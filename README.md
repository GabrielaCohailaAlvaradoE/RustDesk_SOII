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

Proyecto académico para diseñar e implementar una plataforma autohospedada de trazabilidad de sesiones remotas con **RustDesk**, correlacionada con telemetría de Windows. **Estado:** el código alojado aquí es el borrador de la Unidad I; el informe de Unidad II especifica una arquitectura revisada **prevista para la Unidad III**, que todavía no debe darse por desplegada o validada. 

A diferencia de las soluciones comerciales privativas (AnyDesk, TeamViewer), esta arquitectura combina:
1. **Servidor previsto (Debian 12):** RustDesk Server OSS (`hbbs`/`hbbr`), API FastAPI, PostgreSQL y proxy Caddy con TLS 1.3; acceso remoto restringido a la VPN WireGuard. El uso de Ed25519 corresponde a claves de autenticación, no a una afirmación de cifrado Ed25519.
2. **Estaciones Windows previstas:** cinco estaciones Windows 11 con RustDesk, Sysmon (EID 1 y 11, además de eventos 4/16 de estado) y un agente separado en servicio y asistente de sesión. La inactividad se obtiene con `GetLastInputInfo`, sin registrar pulsaciones ni contenido de teclado. Las capturas requieren motivo, horario autorizado y aviso visible.
3. **Privacidad por diseño:** se proyectan retenciones diferenciadas, roles RBAC y TOTP para el dashboard, sin captura de cámara ni teclado. Fuera del horario autorizado solo se prevén metadatos de sesión. La conformidad normativa debe verificarse durante la implementación y no se afirma como certificada.

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

## Estado de la arquitectura: Unidad I frente a Unidad III

| Aspecto | Borrador de Unidad I (código actual) | Diseño de Unidad II (previsto para Unidad III) |
| --- | --- | --- |
| Dashboard/API | FastAPI por HTTP en puerto 8000, sin controles suficientes para exposición pública | Caddy + TLS 1.3 en TCP 443 dentro de WireGuard; API interna sin puerto público |
| Red y acceso remoto | Sin aislamiento VPN suficiente en el borrador | WireGuard; único puerto público previsto UDP 51820; Cloud Firewall y nftables |
| RustDesk | Servicios `hbbs`/`hbbr` del borrador | Servicios restringidos a la VPN; estaciones con acceso a ingesta HTTPS y puertos necesarios de señalización/relay |
| Datos y auditoría | Borrador con controles incompletos | PostgreSQL, controles de acceso RBAC/TOTP, bitácora encadenada, política de retención |
| Capturas | Diseño inicial requiere revisión de privacidad | Solo bajo demanda, con motivo y aviso visible dentro del horario autorizado |

**Importante:** el código y los comandos siguientes corresponden al borrador de Unidad I y **no implementan ni demuestran** todos los controles de la arquitectura de Unidad II. No exponer `8000/TCP` ni los puertos de RustDesk directamente a internet. La implementación integral, las pruebas de seguridad, el despliegue con cinco estaciones y el cumplimiento de los criterios de aceptación quedan **pendientes para la Unidad III**.

## Guía de ejecución del borrador de Unidad I (solo laboratorio aislado)

### 1. Servidor (Linux Debian 12)
```bash
cd server
chmod +x deploy_debian.sh
./deploy_debian.sh
```
En este **borrador de laboratorio**, el dashboard HTTP puede exponerse en `http://<IP_DEBIAN>:8000` según el despliegue heredado. **No es la configuración aprobada para producción ni para la Unidad III.** En el diseño objetivo, el acceso al dashboard será por **HTTPS/TLS 1.3, TCP 443, únicamente a través de WireGuard**, sin publicación pública de la API ni PostgreSQL.

### 2. Clientes (Estaciones Windows)
1. Instalar el cliente oficial de **RustDesk** y configurar la IP del servidor Debian y la llave pública Ed25519.
2. Configurar `client/config.ini` con la IP del servidor y el identificador nominal del estudiante.
3. Ejecutar el agente:
   ```bash
   pip install -r client/requirements.txt
   python client/agent.py
   ```
   *(O compilar con `client/build_exe.bat` para generar el `.exe` portable sin requerir Python).*
