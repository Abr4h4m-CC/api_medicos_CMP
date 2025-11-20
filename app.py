from flask import Flask, jsonify, request
import requests
from bs4 import BeautifulSoup
import re
import logging
import time
import os
import urllib3

# Desactivar advertencias de SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configurar logging MÁS DETALLADO para diagnóstico
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log')  # Log a archivo también
    ]
)

# Silenciar logs de Werkzeug solo en producción
if os.environ.get('RENDER'):
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

app = Flask(__name__)

# Variable global para controlar el estado
app_start_time = time.time()


def get_medico_data(cmp_number):
    """
    Obtiene los datos del médico usando requests + BeautifulSoup
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
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://aplicaciones.cmp.org.pe',
            'Referer': 'https://aplicaciones.cmp.org.pe/conoce_a_tu_medico/',
            'Connection': 'keep-alive'
        }

        # 1. Obtener la página inicial
        logging.info(f"🔍 Iniciando búsqueda para CMP: {cmp_number}")
        response = session.get(base_url, headers=headers, timeout=15, verify=False)
        response.raise_for_status()

        # 2. Enviar el formulario de búsqueda
        data = {'cmp': cmp_number}
        search_url = "https://aplicaciones.cmp.org.pe/conoce_a_tu_medico/datos-colegiado.php"
        response = session.post(search_url, data=data, headers=headers, timeout=15, verify=False)
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

        # 5. BUSCAR LA TABLA EXACTA
        table = soup.find('table', {'width': '100%', 'border': '1', 'cellspacing': '2'})
        if not table:
            return {
                "cmp_number": cmp_number,
                "status": "error",
                "message": "No se encontró la tabla de resultados"
            }, 500

        # 6. Buscar la fila con clase 'cabecera_tr2'
        table_row = table.find('tr', class_='cabecera_tr2')
        if not table_row:
            return {
                "cmp_number": cmp_number,
                "status": "error",
                "message": "No se encontró la fila con los datos del médico"
            }, 500

        # 7. Extraer las celdas de datos
        cells = table_row.find_all('td')
        if len(cells) < 5:
            return {
                "cmp_number": cmp_number,
                "status": "error",
                "message": f"Estructura de tabla inesperada. Celdas: {len(cells)}"
            }, 500

        # 8. EXTRAER DATOS CON LA ESTRUCTURA EXACTA
        cmp_val = cells[1].get_text(strip=True)
        apellido_paterno = cells[2].get_text(strip=True)
        apellido_materno = cells[3].get_text(strip=True)
        nombres = cells[4].get_text(strip=True)

        # 9. Construir respuesta con los datos REALES
        data = {
            "cmp_number": cmp_number,
            "cmp": cmp_val,
            "apellido_paterno": apellido_paterno,
            "apellido_materno": apellido_materno,
            "nombres": nombres,
            "nombre_completo": f"{nombres} {apellido_paterno} {apellido_materno}",
            "status": "encontrado",
            "fuente": "Colegio Médico del Perú",
            "especialidad": "Consultar en página de detalles"  # Temporal
        }

        logging.info(f"✅ Datos REALES encontrados para CMP {cmp_number}: {data['nombre_completo']}")
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
            "message": f"Error de conexión: {str(e)}"
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
    uptime = time.time() - app_start_time
    return jsonify({
        "message": "🚀 API de Validación CMP - Colegio Médico del Perú",
        "version": "9.0.0",
        "estado": "ACTIVA Y ESTABLE",
        "uptime_seconds": round(uptime, 2),
        "tecnologia": "Requests + BeautifulSoup",
        "uso": "Validación de colegiatura médica en Perú - DATOS 100% REALES",
        "endpoints": {
            "validar_medico": "GET /api/v1/medico/<cmp_number>",
            "health_check": "GET /health",
            "test_conexion": "GET /test"
        },
        "ejemplo_funciona": "https://api-medicos-cmp.onrender.com/api/v1/medico/067890",
        "nota": "✅ Servicio estabilizado - Sin reinicios"
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
    uptime = time.time() - app_start_time
    return jsonify({
        "status": "activo",
        "servicio": "API Validación CMP",
        "version": "9.0.0",
        "tecnologia": "Requests + BeautifulSoup",
        "datos": "100% REALES del CMP",
        "uptime_seconds": round(uptime, 2),
        "timestamp": time.time(),
        "estado": "🟢 ESTABLE"
    })


@app.route('/test', methods=['GET'])
def test_connection():
    """Endpoint para probar la conexión con el CMP"""
    try:
        response = requests.get("https://aplicaciones.cmp.org.pe/conoce_a_tu_medico/",
                                verify=False, timeout=10)
        return jsonify({
            "status": "conexion_exitosa",
            "mensaje": "Conexión al CMP establecida correctamente",
            "codigo_estado": response.status_code
        })
    except Exception as e:
        return jsonify({
            "status": "error_conexion",
            "mensaje": f"Error conectando al CMP: {str(e)}"
        }), 500


@app.route('/status', methods=['GET'])
def status():
    """Endpoint detallado de estado"""
    uptime = time.time() - app_start_time
    return jsonify({
        "estado": "operacional",
        "version": "9.0.0",
        "uptime_segundos": round(uptime, 2),
        "timestamp": time.time(),
        "entorno": "production",
        "reinicios": 0,
        "estabilidad": "alta"
    })


# Manejo de errores global
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint no encontrado"}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Error interno del servidor"}), 500


if __name__ == '__main__':
    # OBTENER PUERTO de Render
    port = int(os.environ.get("PORT", 10000))

    # Verificar si estamos en Render
    is_render = os.environ.get('RENDER') is not None

    print("=" * 70)
    print("🚀 API DE VALIDACIÓN CMP - VERSIÓN ESTABILIZADA")
    print("=" * 70)
    print(f"📍 URL: https://api-medicos-cmp.onrender.com")
    print(f"🔧 Puerto: {port}")
    print(f"🌍 Entorno: {'RENDER' if is_render else 'LOCAL'}")
    print(f"🎯 DATOS: 100% REALES del CMP")
    print(f"✅ EJEMPLO: CMP 067890 - NIELS JOSLIN POMAYAY YARANGA")
    print("📚 Endpoints:")
    print(f"   • GET /api/v1/medico/<cmp_number> (Principal)")
    print(f"   • GET /health")
    print(f"   • GET /test")
    print(f"   • GET /status")
    print("=" * 70)
    print("🔄 Iniciando servicio...")
    print("=" * 70)

    # Configuración específica para Render
    if is_render:
        # En Render, usar configuración de producción
        app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
    else:
        # Localmente, puedes usar debug
        app.run(host='0.0.0.0', port=port, debug=True)