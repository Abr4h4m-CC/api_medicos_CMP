#!/usr/bin/env bash
set -e

echo "🚀 Instalando dependencias del sistema..."
apt-get update
apt-get install -y wget gnupg

echo "🔧 Instalando Chrome..."
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list
apt-get update
apt-get install -y google-chrome-stable

echo "📦 Instalando dependencias de Python..."
pip install --upgrade pip
pip install -r requirements.txt

echo "✅ Configuración completada"