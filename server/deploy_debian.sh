#!/bin/bash
# ==============================================================================
# Script de Despliegue Automatizado para Linux Debian 12
# «Tracking and Analyzing Remote Desktop Connection Logs using RustDesk»
# Universidad Privada de Tacna - Sistemas Operativos II
# ==============================================================================

set -e

echo "=== 1. Actualizando paquetes del sistema ==="
sudo apt-get update && sudo apt-get upgrade -y

echo "=== 2. Instalando dependencias básicas y Docker ==="
sudo apt-get install -y curl wget git ufw ca-certificates gnupg lsb-release

if ! command -v docker &> /dev/null; then
    echo "Instalando Docker Engine..."
    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi

echo "=== 3. Configurando Firewall (UFW) para RustDesk y API ==="
sudo ufw allow 21115:21119/tcp
sudo ufw allow 21116/udp
sudo ufw allow 8000/tcp
sudo ufw allow 22/tcp
sudo ufw --force enable

echo "=== 4. Creando carpetas de almacenamiento ==="
mkdir -p data db_data screenshots

echo "=== 5. Levantando contenedores (RustDesk hbbs/hbbr + API Dashboard) ==="
sudo docker compose up -d --build

echo ""
echo "=============================================================================="
echo "¡Despliegue exitoso en Debian 12!"
echo "Dashboard de Supervisión activo en: http://$(hostname -I | awk '{print $1}'):8000"
echo "Para ver la llave pública de RustDesk para los clientes ejecuta:"
echo "cat ./data/id_ed25519.pub"
echo "=============================================================================="
