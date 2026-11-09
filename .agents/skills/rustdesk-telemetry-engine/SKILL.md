---
name: rustdesk-telemetry-engine
description: Guía de ingeniería y procedimientos operativos para el sistema de telemetría forense, auditoría y monitoreo de escritorio remoto con RustDesk, Linux Debian 12, agentes Windows y Dashboard.
---

# Skill: RustDesk Telemetry & Audit Engine (Sistemas Operativos II)

Esta skill proporciona las directrices arquitectónicas, estándares de desarrollo y protocolos de prueba para implementar el sistema de seguimiento y análisis de sesiones de escritorio remoto con RustDesk.

---

## 1. Topología del Sistema y Roles

El sistema se compone de tres módulos desacoplados:

1. **Servidor Central (Linux Debian 12):**
   * **Servicios Core de RustDesk OSS:** `hbbs` (puertos `21115-21116/tcp`, `21116/udp`) para señalización e IDs; `hbbr` (puerto `21117/tcp`) para retransmisión (*relay*).
   * **Criptografía:** Autenticación de clientes mediante pares de llaves asimétricas **Ed25519**.
   * **API de Ingestión (FastAPI):** Recibe telemetría JSON y capturas de pantalla de los clientes. Almacena en base de datos SQLite/PostgreSQL y correlaciona eventos.
   * **Dashboard Web:** Interfaz gráfica para administradores con línea de tiempo forense, filtros por estudiante y visor de capturas de pantalla.

2. **Estaciones de Trabajo Supervisadas (5 Clientes Windows):**
   * **RustDesk Client:** Aplicación oficial configurada con el host de Debian y la clave pública.
   * **Agente Colector (`client/agent.py`):** Script/servicio en segundo plano que extrae:
     * Marcas de inicio y fin de sesión remota desde `%AppData%\RustDesk\log\`.
     * Tiempo de inactividad física del usuario mediante la API Win32 `GetLastInputInfo`.
     * Eventos de Sysmon (EID 1: creación de procesos con línea de comando; EID 11: creación de archivos).
     * Ventana activa en primer plano (`GetForegroundWindow` / `GetWindowText`).
     * Métricas de carga del sistema (`psutil`: CPU, RAM, red).
     * Capturas de pantalla bajo demanda o programadas comprimidas en JPEG.

3. **Mapeo Nominal de Clientes (Estudiantes UPT):**
   * `CLIENT_01_COHAILA`: Cohaila Alvarado, Gabriela Estefania (2022075746)
   * `CLIENT_02_LANCHIPA`: Lanchipa Salinas, Alessandro Giuseppe (2023077278)
   * `CLIENT_03_ALVARADO`: Alvarado Urbano, Saul Jose (2023078332)
   * `CLIENT_04_CALDERON`: Calderon Rodriguez, Juan Carlos (2025001420)
   * `CLIENT_05_LOPEZ`: Lopez Ojeda, Keyla Noelia (2023078690)
   * `CLIENT_06_ESTEBAN`: Esteban Ramos, Ana Cecilia (2023078688)

---

## 2. Estándares Técnicos y de Código

### A. Medición de Inactividad (Win32 API)
Para calcular los segundos de inactividad física sin instalar software invasivo ni keyloggers:
```python
import ctypes

class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

def get_idle_seconds() -> float:
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
        millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
        return max(0.0, millis / 1000.0)
    return 0.0
```

### B. Captura y Compresión de Pantalla
Las capturas deben optimizarse para no saturar el canal de red (< 150 KB por captura):
```python
from io import BytesIO
from PIL import ImageGrab

def capture_screen_jpeg(quality: int = 65) -> bytes:
    screenshot = ImageGrab.grab()
    buffer = BytesIO()
    screenshot.save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()
```

### C. Regla de Correlación Temporal en el Servidor
Un evento de sistema $E_i$ pertenece a una sesión remota $S_k$ si y solo si:
$$(t_{\text{inicio}} \le t_e \le t_{\text{fin}}) \land (\text{HostID}_{E_i} == \text{HostID}_{S_k})$$

---

## 3. Consideraciones Éticas y Legales (Ley N° 31572)

Al implementar o modificar componentes de telemetría:
* **Prohibición de Keyloggers:** No capturar pulsaciones de teclado individuales ni contraseñas.
* **Prohibición de Acceso a Cámaras Web:** No activar cámaras web sin consentimiento explícito.
* **Proporcionalidad:** La captura de pantalla debe ejecutarse bajo demanda para auditoría justificada o con notificación visual al teletrabajador.
* **Desconexión Digital:** Suspender el registro de métricas fuera de los horarios de sesión autorizados.
