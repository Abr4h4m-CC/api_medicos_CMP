import os

from flask import Flask, jsonify, request
import requests
from bs4 import BeautifulSoup
import re
import logging
import time

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)


def get_medico_data(cmp_number):
    """
    Obtiene los datos del médico usando requests + BeautifulSoup (sin navegador)
    """
    cmp_number = str(cmp_number).strip()

    try:
        # URL base y sesión
        session = requests.Session()
        base_url = "https://aplicaciones.cmp.org.pe/conoce_a_tu_medico/"

        # Headers para simular navegador
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.8,en;q=0.5,en-US;q=0.3',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://aplicaciones.cmp.org.pe',
            'Referer': 'https://aplicaciones.cmp.org.pe/conoce_a_tu_medico/',
        }

        # 1. Obtener la página inicial para tener la sesión
        logging.info(f"🔍 Iniciando búsqueda para CMP: {cmp_number}")
        response = session.get(base_url, headers=headers, timeout=30)
        response.raise_for_status()

        # 2. Enviar el formulario de búsqueda
        data = {
            'cmp': cmp_number
        }

        search_url = "https://aplicaciones.cmp.org.pe/conoce_a_tu_medico/datos-colegiado.php"
        response = session.post(search_url, data=data, headers=headers, timeout=30)
        response.raise_for_status()

        # 3. Analizar el HTML de respuesta
        soup = BeautifulSoup(response.text, 'html.parser')

        # 4. Verificar si no hay resultados
        if "No se encontró ningún Colegiado" in response.text:
            return {
                "cmp_number": cmp_number,
                "status": "no_encontrado",
                "message": "No se encontró ningún médico con el CMP proporcionado"
            }, 404

        # 5. Buscar la tabla con los datos
        table_row = soup.find('tr', class_='cabecera_tr2')
        if not table_row:
            return {
                "cmp_number": cmp_number,
                "status": "error",
                "message": "No se encontró la tabla de datos en la respuesta"
            }, 500

        # 6. Extraer las celdas de datos
        cells = table_row.find_all('td')
        if len(cells) < 5:
            return {
                "cmp_number": cmp_number,
                "status": "error",
                "message": "Estructura de tabla inesperada"
            }, 500

        # 7. Construir respuesta con los datos
        data = {
            "cmp_number": cmp_number,
            "cmp": cells[1].get_text(strip=True),
            "apellido_paterno": cells[2].get_text(strip=True),
            "apellido_materno": cells[3].get_text(strip=True),
            "nombres": cells[4].get_text(strip=True),
            "nombre_completo": f"{cells[4].get_text(strip=True)} {cells[2].get_text(strip=True)} {cells[3].get_text(strip=True)}",
            "status": "encontrado",
            "fuente": "Colegio Médico del Perú"
        }

        # 8. Buscar especialidad
        try:
            # Buscar en todo el HTML la línea que contiene "Especialidad:"
            especialidad_text = soup.find(string=re.compile(r'Especialidad:'))
            if especialidad_text:
                match = re.search(r'Especialidad:\s*(.*)', especialidad_text)
                if match:
                    data["especialidad"] = match.group(1).strip()
                else:
                    data["especialidad"] = "No disponible"
            else:
                data["especialidad"] = "No disponible"
        except Exception as e:
            logging.warning(f"⚠️ No se pudo obtener especialidad: {e}")
            data["especialidad"] = "No disponible"

        logging.info(f"✅ Datos encontrados para CMP {cmp_number}: {data['nombres']}")
        return data, 200

    except requests.exceptions.Timeout:
        return {
            "cmp_number": cmp_number,
            "status": "error",
            "message": "Tiempo de espera agotado al consultar el CMP"
        }, 500
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Error de conexión: {e}")
        return {
            "cmp_number": cmp_number,
            "status": "error",
            "message": f"Error de conexión con el servidor del CMP: {str(e)}"
        }, 500
    except Exception as e:
        logging.error(f"❌ Error inesperado: {e}")
        return {
            "cmp_number": cmp_number,
            "status": "error",
            "message": f"Error inesperado: {str(e)}"
        }, 500


@app.route('/')
def home():
    return jsonify({
        "message": "🚀 API de Validación CMP - Colegio Médico del Perú",
        "version": "5.0.0",
        "estado": "ACTIVA",
        "tecnologia": "Requests + BeautifulSoup (Sin navegador)",
        "uso": "Validación de colegiatura médica en Perú",
        "endpoints": {
            "validar_medico": "GET /api/v1/medico/<cmp_number>",
            "health_check": "GET /health",
            "documentacion": "GET /"
        },
        "ejemplo": "https://api-medicos-cmp.onrender.com/api/v1/medico/067890",
        "nota": "✅ Esta versión es más rápida y confiable - Sin dependencias de navegador"
    })


@app.route('/api/v1/medico/<cmp_number>', methods=['GET'])
def get_medico(cmp_number):
    """Endpoint principal para validar CMP"""
    if not cmp_number or not re.match(r'^\d+$', cmp_number.strip()):
        return jsonify({
            "status": "error_validacion",
            "message": "El número CMP debe contener solo dígitos numéricos"
        }), 400

    data, status_code = get_medico_data(cmp_number.strip())
    return jsonify(data), status_code


@app.route('/health', methods=['GET'])
def health_check():
    """Endpoint de salud del servicio"""
    return jsonify({
        "status": "activo",
        "servicio": "API Validación CMP",
        "version": "5.0.0",
        "tecnologia": "Requests + BeautifulSoup",
        "timestamp": time.time(),
        "rendimiento": "Óptimo - Sin navegador"
    })


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))

    print("=" * 60)
    print("🚀 API DE VALIDACIÓN CMP - VERSIÓN DEFINITIVA")
    print("=" * 60)
    print(f"📍 URL: https://api-medicos-cmp.onrender.com")
    print(f"🔧 Puerto: {port}")
    print(f"⚡ Tecnología: Requests + BeautifulSoup")
    print(f"🎯 Ventajas: Más rápido, más confiable, sin navegador")
    print("📚 Endpoints:")
    print(f"   • GET /api/v1/medico/<cmp_number>")
    print(f"   • GET /health")
    print("=" * 60)
    print("✅ Iniciando servicio...")
    print("=" * 60)

    app.run(host='0.0.0.0', port=port, debug=False)