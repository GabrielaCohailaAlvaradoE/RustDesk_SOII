"""
Agente de Telemetría Robusto para Windows
Tracking and Analyzing Remote Desktop Connection Logs using RustDesk
Universidad Privada de Tacna - Sistemas Operativos II

Características:
1. Inactividad física mediante Win32 API (GetLastInputInfo).
2. Detección de sesión activa de RustDesk (%AppData%\\RustDesk\\log).
3. Extracción de eventos de Sysmon (EID 1: Procesos, EID 11: Archivos).
4. Módulo de captura de pantalla comprimida (JPEG) bajo demanda.
5. Buffer local SQLite (resistencia ante caídas de red o reinicios de Debian).
"""

import os
import sys
import time
import json
import socket
import logging
import sqlite3
import configparser
import ctypes
import subprocess
from datetime import datetime, timezone
from io import BytesIO

import requests
import psutil
from PIL import ImageGrab

# Configuración de Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("agent_activity.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("RustDeskAgent")

# ----------------------------------------------------------------------
# 1. API Win32: Inactividad y Foco de Ventana
# ----------------------------------------------------------------------
class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def get_idle_seconds() -> float:
    """Calcula los segundos sin interacción física de mouse o teclado."""
    try:
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
            return max(0.0, millis / 1000.0)
    except Exception as e:
        logger.debug(f"Error en GetLastInputInfo: {e}")
    return 0.0


def get_foreground_window_title() -> str:
    """Obtiene el título de la ventana activa en primer plano."""
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
            return buff.value
    except Exception as e:
        logger.debug(f"Error en GetForegroundWindow: {e}")
    return "Sin foco / Escritorio"


# ----------------------------------------------------------------------
# 2. Extractor de Eventos de Sysmon (EID 1 y EID 11)
# ----------------------------------------------------------------------
def get_recent_sysmon_events(max_events: int = 5) -> list:
    """
    Consulta los eventos recientes de Microsoft-Windows-Sysmon/Operational
    usando PowerShell nativo de Windows.
    EID 1: Creación de proceso
    EID 11: Creación de archivo
    """
    events = []
    try:
        cmd = [
            "powershell", "-NoProfile", "-Command",
            f"Get-WinEvent -LogName 'Microsoft-Windows-Sysmon/Operational' -MaxEvents {max_events} -ErrorAction SilentlyContinue | "
            "Select-Object Id, TimeCreated, Message | ConvertTo-Json"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        if res.returncode == 0 and res.stdout.strip():
            raw_data = json.loads(res.stdout)
            if isinstance(raw_data, dict):
                raw_data = [raw_data]
            for item in raw_data:
                msg = item.get("Message", "")
                first_line = msg.split("\n")[0] if msg else "Sysmon Event"
                events.append({
                    "event_id": item.get("Id"),
                    "time": str(item.get("TimeCreated")),
                    "summary": first_line[:120]
                })
    except Exception as e:
        logger.debug(f"Sysmon no disponible o error de lectura: {e}")
    return events


# ----------------------------------------------------------------------
# 3. Lector de Sesiones de RustDesk
# ----------------------------------------------------------------------
def check_rustdesk_active_session() -> dict:
    appdata = os.environ.get("APPDATA", "")
    log_dir = os.path.join(appdata, "RustDesk", "log")
    
    session_info = {
        "is_remote_active": False,
        "remote_id": "N/A",
        "last_log_entry": ""
    }
    
    if not os.path.exists(log_dir):
        return session_info
        
    try:
        log_files = [os.path.join(log_dir, f) for f in os.listdir(log_dir) if f.endswith(".log")]
        if not log_files:
            return session_info
            
        latest_file = max(log_files, key=os.path.getmtime)
        with open(latest_file, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            if lines:
                recent_lines = lines[-15:]
                session_info["last_log_entry"] = recent_lines[-1].strip()
                for l in reversed(recent_lines):
                    l_lower = l.lower()
                    if "established" in l_lower or "login" in l_lower:
                        session_info["is_remote_active"] = True
                        break
                    elif "closed" in l_lower or "disconnected" in l_lower:
                        session_info["is_remote_active"] = False
                        break
    except Exception as e:
        logger.debug(f"Error inspeccionando logs de RustDesk: {e}")
        
    return session_info


# ----------------------------------------------------------------------
# 4. Captura de Pantalla Comprimida
# ----------------------------------------------------------------------
def capture_screen_bytes(quality: int = 65) -> bytes:
    try:
        img = ImageGrab.grab()
        if img.mode != "RGB":
            img = img.convert("RGB")
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        return buffer.getvalue()
    except Exception as e:
        logger.error(f"Error en captura de pantalla: {e}")
        return b""


# ----------------------------------------------------------------------
# 5. Búfer Local SQLite (Resistencia a Desconexiones)
# ----------------------------------------------------------------------
class LocalBuffer:
    def __init__(self, db_path: str = "offline_buffer.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """)

    def push(self, payload: dict):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO pending_telemetry (payload_json, created_at) VALUES (?, ?)",
                    (json.dumps(payload), datetime.now(timezone.utc).isoformat())
                )
        except Exception as e:
            logger.error(f"Error guardando en buffer local: {e}")

    def pop_all(self) -> list:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, payload_json FROM pending_telemetry ORDER BY id ASC LIMIT 50")
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error leyendo buffer local: {e}")
            return []

    def remove(self, ids: list):
        if not ids:
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.executemany("DELETE FROM pending_telemetry WHERE id = ?", [(i,) for i in ids])
        except Exception as e:
            logger.error(f"Error eliminando de buffer local: {e}")


# ----------------------------------------------------------------------
# 6. Agente Principal de Telemetría
# ----------------------------------------------------------------------
class TelemetryAgent:
    def __init__(self, config_path: str = "config.ini"):
        self.config = configparser.ConfigParser()
        if not os.path.exists(config_path):
            logger.error(f"Falta config.ini en {os.path.abspath(config_path)}")
            sys.exit(1)
            
        self.config.read(config_path, encoding="utf-8")
        
        self.server_host = self.config.get("SERVER", "host", fallback="127.0.0.1")
        self.server_port = self.config.getint("SERVER", "port", fallback=8000)
        self.protocol = self.config.get("SERVER", "protocol", fallback="http")
        self.api_token = self.config.get("SERVER", "api_token", fallback="")
        
        self.client_id = self.config.get("CLIENT", "client_id", fallback="CLIENT_01_UNKNOWN")
        self.student_name = self.config.get("CLIENT", "student_name", fallback="Alumno UPT")
        
        self.heartbeat_interval = self.config.getint("TELEMETRY", "heartbeat_interval", fallback=5)
        self.idle_threshold = self.config.getint("TELEMETRY", "idle_threshold_seconds", fallback=60)
        self.enable_sysmon = self.config.getboolean("TELEMETRY", "enable_sysmon", fallback=True)
        self.auto_screenshot_interval = self.config.getint("TELEMETRY", "auto_screenshot_interval", fallback=300)
        self.screenshot_quality = self.config.getint("TELEMETRY", "screenshot_quality", fallback=65)
        
        self.base_url = f"{self.protocol}://{self.server_host}:{self.server_port}/api/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "X-Client-ID": self.client_id
        }
        
        self.buffer = LocalBuffer()
        self.last_screenshot_time = time.time()
        logger.info(f"Agente inicializado para: {self.client_id} ({self.student_name})")
        logger.info(f"Destino Debian: {self.base_url}")

    def collect_payload(self) -> dict:
        idle_secs = get_idle_seconds()
        is_idle = idle_secs >= self.idle_threshold
        rustdesk_data = check_rustdesk_active_session()
        
        sysmon_events = get_recent_sysmon_events(max_events=3) if self.enable_sysmon else []
        
        payload = {
            "client_id": self.client_id,
            "student_name": self.student_name,
            "hostname": socket.gethostname(),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "idle_seconds": round(idle_secs, 1),
            "is_idle": is_idle,
            "foreground_window": get_foreground_window_title(),
            "cpu_percent": psutil.cpu_percent(interval=None),
            "ram_percent": psutil.virtual_memory().percent,
            "rustdesk_session": rustdesk_data,
            "sysmon_events": sysmon_events
        }
        return payload

    def flush_offline_buffer(self):
        """Intenta enviar datos que quedaron guardados durante cortes de red."""
        pending = self.buffer.pop_all()
        if not pending:
            return
            
        success_ids = []
        url = f"{self.base_url}/telemetry"
        for row_id, raw_json in pending:
            try:
                payload = json.loads(raw_json)
                resp = requests.post(url, json=payload, headers=self.headers, timeout=3)
                if resp.status_code == 200:
                    success_ids.append(row_id)
                else:
                    break
            except Exception:
                break
                
        if success_ids:
            self.buffer.remove(success_ids)
            logger.info(f"Buffer offline sincronizado: {len(success_ids)} registros enviados a Debian.")

    def send_telemetry(self, payload: dict):
        url = f"{self.base_url}/telemetry"
        try:
            resp = requests.post(url, json=payload, headers=self.headers, timeout=4)
            if resp.status_code == 200:
                data = resp.json()
                logger.info(f"OK | Inactivo: {payload['idle_seconds']}s | CPU: {payload['cpu_percent']}% | RAM: {payload['ram_percent']}% | Remoto: {payload['rustdesk_session']['is_remote_active']}")
                
                # Si se sincronizó el actual, vaciar la cola offline
                self.flush_offline_buffer()
                
                # Revisar si el supervisor pidió captura inmediata desde el Dashboard
                if data.get("request_screenshot", False):
                    logger.info("Orden de captura bajo demanda recibida desde el Dashboard.")
                    self.send_screenshot(trigger="demand")
            else:
                logger.warning(f"Error servidor: HTTP {resp.status_code}. Guardando en buffer local...")
                self.buffer.push(payload)
        except requests.exceptions.RequestException:
            logger.warning("Servidor Debian no responde. Registro guardado en buffer offline.")
            self.buffer.push(payload)

    def send_screenshot(self, trigger: str = "periodic"):
        url = f"{self.base_url}/screenshot"
        img_bytes = capture_screen_bytes(quality=self.screenshot_quality)
        if not img_bytes:
            return
            
        files = {"file": ("screenshot.jpg", img_bytes, "image/jpeg")}
        data = {
            "client_id": self.client_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "trigger": trigger,
            "window_title": get_foreground_window_title()
        }
        try:
            resp = requests.post(url, files=files, data=data, headers=self.headers, timeout=8)
            if resp.status_code == 200:
                logger.info(f"Captura transmitida con éxito ({len(img_bytes)/1024:.1f} KB, trigger: {trigger}).")
            else:
                logger.warning(f"Fallo captura: HTTP {resp.status_code}")
        except Exception as e:
            logger.warning(f"No se pudo enviar captura de pantalla: {e}")

    def run(self):
        logger.info("Iniciando monitoreo de telemetría y auditoría continua...")
        while True:
            try:
                payload = self.collect_payload()
                self.send_telemetry(payload)
                
                if self.auto_screenshot_interval > 0:
                    now = time.time()
                    if now - self.last_screenshot_time >= self.auto_screenshot_interval:
                        self.send_screenshot(trigger="periodic")
                        self.last_screenshot_time = now
            except KeyboardInterrupt:
                logger.info("Agente detenido por el usuario.")
                break
            except Exception as e:
                logger.error(f"Error en ciclo principal: {e}")
                
            time.sleep(self.heartbeat_interval)


if __name__ == "__main__":
    agent = TelemetryAgent()
    agent.run()
