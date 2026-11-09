"""
API Backend de Ingestión y Servidor del Dashboard de Supervisión
Tracking and Analyzing Remote Desktop Connection Logs using RustDesk
Linux Debian 12 / FastAPI
"""

import os
import sqlite3
import shutil
import json
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import FastAPI, Header, HTTPException, UploadFile, File, Form, Depends
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

# Inicialización de directorios
DATA_DIR = os.getenv("DATA_DIR", "./data")
SCREENSHOTS_DIR = os.getenv("SCREENSHOTS_DIR", "./screenshots")
DB_PATH = os.path.join(DATA_DIR, "telemetry_audit.db")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

EXPECTED_TOKEN = os.getenv("API_TOKEN", "SECRET_TOKEN_UPT_2026")

app = FastAPI(title="RustDesk Telemetry & Audit API", version="1.0.0")

# ----------------------------------------------------------------------
# 1. Base de Datos SQLite
# ----------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Telemetría continua
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS telemetry_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id TEXT NOT NULL,
        student_name TEXT,
        hostname TEXT,
        timestamp_utc TEXT,
        idle_seconds REAL,
        is_idle INTEGER,
        foreground_window TEXT,
        cpu_percent REAL,
        ram_percent REAL,
        is_remote_active INTEGER,
        remote_id TEXT,
        sysmon_json TEXT
    )
    """)
    
    # Capturas de pantalla registradas
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS screenshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id TEXT NOT NULL,
        filename TEXT NOT NULL,
        timestamp_utc TEXT,
        trigger_mode TEXT,
        window_title TEXT
    )
    """)
    
    # Órdenes pendientes (captura bajo demanda)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pending_commands (
        client_id TEXT PRIMARY KEY,
        request_screenshot INTEGER DEFAULT 0
    )
    """)
    
    conn.commit()
    conn.close()

init_db()

# ----------------------------------------------------------------------
# 2. Esquemas Pydantic y Seguridad
# ----------------------------------------------------------------------
class RustDeskSession(BaseModel):
    is_remote_active: bool
    remote_id: Optional[str] = "N/A"
    last_log_entry: Optional[str] = ""

class SysmonEvent(BaseModel):
    event_id: Optional[int] = None
    time: Optional[str] = None
    summary: Optional[str] = None

class TelemetryPayload(BaseModel):
    client_id: str
    student_name: str
    hostname: str
    timestamp_utc: str
    idle_seconds: float
    is_idle: bool
    foreground_window: str
    cpu_percent: float
    ram_percent: float
    rustdesk_session: RustDeskSession
    sysmon_events: Optional[List[SysmonEvent]] = []

def verify_token(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token de autorización faltante.")
    token = authorization.split(" ")[1]
    if token != EXPECTED_TOKEN:
        raise HTTPException(status_code=403, detail="Token no autorizado.")
    return token

# ----------------------------------------------------------------------
# 3. Endpoints de Ingestión
# ----------------------------------------------------------------------
@app.post("/api/v1/telemetry")
def receive_telemetry(payload: TelemetryPayload, token: str = Depends(verify_token)):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    sysmon_serialized = json.dumps([e.dict() for e in payload.sysmon_events]) if payload.sysmon_events else "[]"
    
    cursor.execute("""
    INSERT INTO telemetry_logs (
        client_id, student_name, hostname, timestamp_utc, idle_seconds, 
        is_idle, foreground_window, cpu_percent, ram_percent, is_remote_active, remote_id, sysmon_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        payload.client_id,
        payload.student_name,
        payload.hostname,
        payload.timestamp_utc,
        payload.idle_seconds,
        1 if payload.is_idle else 0,
        payload.foreground_window,
        payload.cpu_percent,
        payload.ram_percent,
        1 if payload.rustdesk_session.is_remote_active else 0,
        payload.rustdesk_session.remote_id,
        sysmon_serialized
    ))
    
    # Revisar si hay una orden de captura pendiente
    cursor.execute("SELECT request_screenshot FROM pending_commands WHERE client_id = ?", (payload.client_id,))
    row = cursor.fetchone()
    request_screenshot = False
    if row and row[0] == 1:
        request_screenshot = True
        cursor.execute("UPDATE pending_commands SET request_screenshot = 0 WHERE client_id = ?", (payload.client_id,))
        
    conn.commit()
    conn.close()
    
    return {
        "status": "success",
        "client_id": payload.client_id,
        "request_screenshot": request_screenshot
    }

@app.post("/api/v1/screenshot")
async def receive_screenshot(
    file: UploadFile = File(...),
    client_id: str = Form(...),
    timestamp_utc: str = Form(...),
    trigger: str = Form("demand"),
    window_title: str = Form(""),
    token: str = Depends(verify_token)
):
    safe_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{client_id}_{safe_ts}.jpg"
    file_path = os.path.join(SCREENSHOTS_DIR, filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO screenshots (client_id, filename, timestamp_utc, trigger_mode, window_title)
    VALUES (?, ?, ?, ?, ?)
    """, (client_id, filename, timestamp_utc, trigger, window_title))
    conn.commit()
    conn.close()
    
    return {"status": "saved", "filename": filename}

@app.get("/api/v1/screenshot/download/{filename}")
def download_screenshot(filename: str):
    file_path = os.path.join(SCREENSHOTS_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Captura no encontrada")

# ----------------------------------------------------------------------
# 4. Endpoints del Dashboard y Forense
# ----------------------------------------------------------------------
@app.get("/api/v1/dashboard/summary")
def get_dashboard_summary():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
    SELECT t1.* FROM telemetry_logs t1
    INNER JOIN (
        SELECT client_id, MAX(id) as max_id
        FROM telemetry_logs
        GROUP BY client_id
    ) t2 ON t1.id = t2.max_id
    ORDER BY t1.client_id ASC
    """)
    rows = cursor.fetchall()
    
    clients = []
    for r in rows:
        sysmon_events = json.loads(r["sysmon_json"]) if r["sysmon_json"] else []
        clients.append({
            "client_id": r["client_id"],
            "student_name": r["student_name"],
            "hostname": r["hostname"],
            "last_seen": r["timestamp_utc"],
            "idle_seconds": r["idle_seconds"],
            "is_idle": bool(r["is_idle"]),
            "foreground_window": r["foreground_window"],
            "cpu_percent": r["cpu_percent"],
            "ram_percent": r["ram_percent"],
            "is_remote_active": bool(r["is_remote_active"]),
            "latest_sysmon": sysmon_events[:2]
        })
        
    conn.close()
    return {"clients": clients}

@app.post("/api/v1/dashboard/request-screenshot/{client_id}")
def trigger_screenshot_order(client_id: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO pending_commands (client_id, request_screenshot)
    VALUES (?, 1)
    ON CONFLICT(client_id) DO UPDATE SET request_screenshot = 1
    """, (client_id,))
    conn.commit()
    conn.close()
    return {"status": "order_queued", "client_id": client_id}

@app.get("/api/v1/dashboard/screenshots/{client_id}")
def get_client_screenshots(client_id: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM screenshots 
    WHERE client_id = ? 
    ORDER BY id DESC LIMIT 20
    """, (client_id,))
    rows = cursor.fetchall()
    results = [dict(r) for r in rows]
    conn.close()
    return {"screenshots": results}

@app.get("/api/v1/dashboard/timeline/{client_id}")
def get_client_timeline(client_id: str, limit: int = 50):
    """Retorna la reconstrucción cronológica forense de la estación."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, timestamp_utc, idle_seconds, is_idle, foreground_window, is_remote_active, cpu_percent, ram_percent, sysmon_json
    FROM telemetry_logs 
    WHERE client_id = ? 
    ORDER BY id DESC LIMIT ?
    """, (client_id, limit))
    rows = cursor.fetchall()
    timeline = []
    for r in rows:
        item = dict(r)
        item["sysmon_events"] = json.loads(item["sysmon_json"]) if item.get("sysmon_json") else []
        timeline.append(item)
    conn.close()
    return {"timeline": timeline}

# ----------------------------------------------------------------------
# 5. Vista HTML del Dashboard de Supervisión
# ----------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def index_dashboard():
    return """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>RustDesk Telemetry & Audit Dashboard</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-900 text-slate-100 min-h-screen p-6">
        <header class="max-w-7xl mx-auto mb-8 border-b border-slate-700 pb-4 flex justify-between items-center">
            <div>
                <h1 class="text-2xl font-bold text-sky-400">RustDesk Telemetry & Audit Engine</h1>
                <p class="text-sm text-slate-400">Sistemas Operativos II - Universidad Privada de Tacna</p>
            </div>
            <div class="text-right">
                <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-emerald-900 text-emerald-300">
                    Servidor Linux Debian 12 (Activo)
                </span>
            </div>
        </header>

        <main class="max-w-7xl mx-auto space-y-6">
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6" id="clientsGrid">
                <div class="p-6 bg-slate-800 rounded-lg text-center text-slate-400 col-span-full">Cargando estaciones de trabajo...</div>
            </div>

            <!-- Modal de Galería de Capturas -->
            <div id="screenshotModal" class="hidden fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50">
                <div class="bg-slate-800 rounded-lg max-w-4xl w-full p-6 space-y-4 max-h-[90vh] overflow-y-auto">
                    <div class="flex justify-between items-center border-b border-slate-700 pb-2">
                        <h3 class="text-lg font-bold text-sky-300" id="modalTitle">Capturas de Pantalla</h3>
                        <button onclick="closeModal('screenshotModal')" class="text-slate-400 hover:text-white">&times; Cerrar</button>
                    </div>
                    <div id="modalGallery" class="grid grid-cols-1 md:grid-cols-2 gap-4"></div>
                </div>
            </div>

            <!-- Modal de Línea de Tiempo Forense -->
            <div id="timelineModal" class="hidden fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50">
                <div class="bg-slate-800 rounded-lg max-w-4xl w-full p-6 space-y-4 max-h-[90vh] overflow-y-auto">
                    <div class="flex justify-between items-center border-b border-slate-700 pb-2">
                        <h3 class="text-lg font-bold text-emerald-300" id="timelineTitle">Línea de Tiempo Forense</h3>
                        <button onclick="closeModal('timelineModal')" class="text-slate-400 hover:text-white">&times; Cerrar</button>
                    </div>
                    <div id="timelineContent" class="space-y-2 text-xs"></div>
                </div>
            </div>
        </main>

        <script>
            async function fetchSummary() {
                try {
                    const res = await fetch('/api/v1/dashboard/summary');
                    const data = await res.json();
                    renderClients(data.clients);
                } catch(e) {
                    console.error("Error al obtener telemetría:", e);
                }
            }

            function renderClients(clients) {
                const grid = document.getElementById('clientsGrid');
                if(!clients || clients.length === 0) {
                    grid.innerHTML = '<div class="p-6 bg-slate-800 rounded-lg text-slate-400 col-span-full text-center">Esperando conexión de clientes Windows...</div>';
                    return;
                }
                grid.innerHTML = clients.map(c => `
                    <div class="bg-slate-800 rounded-xl p-5 border border-slate-700 space-y-4 shadow-lg">
                        <div class="flex justify-between items-start">
                            <div>
                                <h2 class="font-bold text-lg text-white">${c.client_id}</h2>
                                <p class="text-xs text-slate-400">${c.student_name}</p>
                            </div>
                            <span class="px-2 py-1 rounded text-xs font-semibold ${c.is_remote_active ? 'bg-amber-900 text-amber-300' : 'bg-slate-700 text-slate-300'}">
                                ${c.is_remote_active ? 'Sesión Remota Activa' : 'Local'}
                            </span>
                        </div>

                        <div class="text-xs space-y-1 bg-slate-900/60 p-3 rounded-lg">
                            <p><span class="text-slate-400">Ventana activa:</span> <span class="font-mono text-sky-300 truncate block">${c.foreground_window}</span></p>
                            <p><span class="text-slate-400">Inactividad:</span> <span class="${c.is_idle ? 'text-rose-400 font-bold' : 'text-emerald-400'}">${c.idle_seconds}s ${c.is_idle ? '(Inactivo)' : ''}</span></p>
                            <p><span class="text-slate-400">CPU / RAM:</span> ${c.cpu_percent}% / ${c.ram_percent}%</p>
                        </div>

                        <div class="grid grid-cols-3 gap-2 pt-2">
                            <button onclick="requestScreenshot('${c.client_id}')" class="bg-sky-600 hover:bg-sky-500 text-white text-[11px] py-2 px-2 rounded-lg transition font-medium">
                                Captura
                            </button>
                            <button onclick="viewScreenshots('${c.client_id}')" class="bg-slate-700 hover:bg-slate-600 text-slate-200 text-[11px] py-2 px-2 rounded-lg transition">
                                Galería
                            </button>
                            <button onclick="viewTimeline('${c.client_id}')" class="bg-emerald-700 hover:bg-emerald-600 text-white text-[11px] py-2 px-2 rounded-lg transition">
                                Timeline
                            </button>
                        </div>
                    </div>
                `).join('');
            }

            async function requestScreenshot(clientId) {
                try {
                    await fetch('/api/v1/dashboard/request-screenshot/' + clientId, { method: 'POST' });
                    alert('Orden de captura enviada a ' + clientId + '. Se ejecutará en el próximo ciclo.');
                } catch(e) {
                    alert('Error enviando orden.');
                }
            }

            async function viewScreenshots(clientId) {
                document.getElementById('modalTitle').innerText = 'Capturas de ' + clientId;
                const gallery = document.getElementById('modalGallery');
                gallery.innerHTML = '<p class="text-slate-400 col-span-full">Cargando capturas...</p>';
                document.getElementById('screenshotModal').classList.remove('hidden');

                const res = await fetch('/api/v1/dashboard/screenshots/' + clientId);
                const data = await res.json();
                if(data.screenshots.length === 0) {
                    gallery.innerHTML = '<p class="text-slate-400 col-span-full">No hay capturas registradas aún.</p>';
                    return;
                }
                gallery.innerHTML = data.screenshots.map(s => `
                    <div class="bg-slate-900 p-2 rounded-lg space-y-1">
                        <img src="/api/v1/screenshot/download/${s.filename}" class="w-full rounded h-48 object-cover border border-slate-700 hover:scale-105 transition" />
                        <p class="text-[10px] text-slate-400">${s.timestamp_utc} | ${s.trigger_mode}</p>
                        <p class="text-[10px] text-sky-400 truncate">${s.window_title}</p>
                    </div>
                `).join('');
            }

            async function viewTimeline(clientId) {
                document.getElementById('timelineTitle').innerText = 'Timeline Forense: ' + clientId;
                const content = document.getElementById('timelineContent');
                content.innerHTML = '<p class="text-slate-400">Cargando eventos...</p>';
                document.getElementById('timelineModal').classList.remove('hidden');

                const res = await fetch('/api/v1/dashboard/timeline/' + clientId);
                const data = await res.json();
                if(data.timeline.length === 0) {
                    content.innerHTML = '<p class="text-slate-400">Sin eventos aún.</p>';
                    return;
                }
                content.innerHTML = data.timeline.map(t => `
                    <div class="p-2 rounded border border-slate-700 bg-slate-900 flex justify-between items-center">
                        <div>
                            <span class="text-slate-400 font-mono">[${t.timestamp_utc.split('T')[1].slice(0,8)}]</span>
                            <span class="${t.is_remote_active ? 'text-amber-400 font-bold' : 'text-slate-300'}">
                                ${t.is_remote_active ? 'SESIÓN REMOTA' : 'ACTIVIDAD LOCAL'}
                            </span>
                            - <span class="text-sky-300">${t.foreground_window}</span>
                        </div>
                        <div class="text-right">
                            <span class="${t.is_idle ? 'text-rose-400' : 'text-emerald-400'}">${t.idle_seconds}s inactivo</span>
                        </div>
                    </div>
                `).join('');
            }

            function closeModal(modalId) {
                document.getElementById(modalId).classList.add('hidden');
            }

            setInterval(fetchSummary, 3000);
            fetchSummary();
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
