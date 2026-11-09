# Tracking and Analyzing Remote Desktop Connection Logs using RustDesk

**Curso:** Sistemas Operativos II  
**Institución:** Universidad Privada de Tacna  
**Docente:** Ing. Renzo Taco Coayla  

## Integrantes del Proyecto
1. Cohaila Alvarado, Gabriela Estefania (2022075746)
2. Lanchipa Salinas, Alessandro Giuseppe (2023077278)
3. Alvarado Urbano, Saul Jose (2023078332)
4. Calderon Rodriguez, Juan Carlos (2025001420)
5. Lopez Ojeda, Keyla Noelia (2023078690)
6. Esteban Ramos, Ana Cecilia (2023078688)

---

## Descripción del Proyecto

Sistema soberano y autohospedado (*self-hosted*) para la supervisión, auditoría forense y rastreo de sesiones de escritorio remoto utilizando **RustDesk**. 

A diferencia de las soluciones comerciales privativas (AnyDesk, TeamViewer), esta arquitectura combina:
1. **Infraestructura Central en Linux Debian 12:** Servicios `hbbs` y `hbbr` de RustDesk Server OSS con cifrado Ed25519, junto a una API REST en FastAPI y un Dashboard Web de supervisión en tiempo real.
2. **Telemetría en Estaciones de Trabajo Windows:** Agente en segundo plano que correlaciona marcas de sesión con llamadas a la API Win32 `GetLastInputInfo` (inactividad física real), eventos de Sysmon (EID 1: Procesos, EID 11: Archivos) y capturas de pantalla bajo demanda.
3. **Marco Legal y Ético:** Cumplimiento estricto del principio de proporcionalidad y no invasividad bajo la **Ley de Teletrabajo del Perú (Ley N° 31572)**.

---

## Estructura del Repositorio

```text
├── client/                     # Agente de telemetría para estaciones Windows
│   ├── agent.py                # Script principal (inactividad, Sysmon, capturas)
│   ├── config.ini              # Archivo de configuración (IP, Token, ID alumno)
│   ├── build_exe.bat           # Compilador a ejecutable portable .EXE
│   └── requirements.txt        # Dependencias del cliente
│
├── server/                     # Servidor central en Linux Debian 12
│   ├── docker-compose.yml      # Despliegue de RustDesk (hbbs/hbbr) y API
│   ├── main.py                 # Backend FastAPI + Dashboard Web HTML5
│   ├── Dockerfile              # Contenedor Docker de la API
│   ├── deploy_debian.sh        # Script automatizado de despliegue en Debian 12
│   └── requirements.txt        # Dependencias del servidor
│
├── INFORME_CIENTIFICO_01_RUSTDESK.md  # Informe formal completo con normas APA 7
├── SECCION_3_METODOLOGIA.md           # Metodología y matriz de los 40 artículos
└── .gitignore                  # Exclusión de temporales, bases de datos y logs
```

---

## Guía de Despliegue Rápido

### 1. Servidor (Linux Debian 12)
```bash
cd server
chmod +x deploy_debian.sh
./deploy_debian.sh
```
El Dashboard Web quedará accesible en: `http://<IP_DEBIAN>:8000`.

### 2. Clientes (Estaciones Windows)
1. Instalar el cliente oficial de **RustDesk** y configurar la IP del servidor Debian y la llave pública Ed25519.
2. Configurar `client/config.ini` con la IP del servidor y el identificador nominal del estudiante.
3. Ejecutar el agente:
   ```bash
   pip install -r client/requirements.txt
   python client/agent.py
   ```
   *(O compilar con `client/build_exe.bat` para generar el `.exe` portable sin requerir Python).*
