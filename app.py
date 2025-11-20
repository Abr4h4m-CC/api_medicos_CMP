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

# Configurar logging DETALLADO
logging.basicConfig(
    level=logging.DEBUG,  # Cambiado a DEBUG para más detalles
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Silenciar logs de Werkzeug solo en producción
if os.environ.get('RENDER'):
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

app = Flask(__name__)
app_start_time = time.time()


def debug_html_response(html, cmp_number):
    """Función para debuggear el HTML recibido"""
    debug_info = {
        "cmp_number": cmp_number,
        "html_length": len(html),
        "contains_no_results": "No se encontró ningún Colegiado" in html,
        "contains_table_tag": "<table" in html,
        "contains_cabecera_tr2": "cabecera_tr2" in html,
        "contains_cmp_number": cmp_number in html,
        "sample_html": html[:1000] + "..." if len(html) > 1000 else html
    }
    return debug_info


def get_medico_data(cmp_number):
    """
    Obtiene los datos del médico con debugging completo
    """
    cmp_number = str(cmp_number).strip()

    try:
        # URL base y sesión
        session = requests.Session()
        base_url = "https://aplicaciones.cmp.org.pe/conoce_a_tu_medico/"

        # Headers mejorados
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://aplicaciones.cmp.org.pe',
            'Referer': 'https://aplicaciones.cmp.org.pe/conoce_a_tu_medico/',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache'
        }

        # 1. Obtener la página inicial
        logging.info(f"🔍 Paso 1: Obteniendo página inicial para CMP: {cmp_number}")
        response = session.get(base_url, headers=headers, timeout=20, verify=False)
        response.raise_for_status()
        logging.info(f"✅ Página inicial obtenida. Status: {response.status_code}")

        # 2. Enviar el formulario de búsqueda
        data = {'cmp': cmp_number}
        search_url = "https://aplicaciones.cmp.org.pe/conoce_a_tu_medico/datos-colegiado.php"

        logging.info(f"🔍 Paso 2: Enviando formulario a {search_url}")
        response = session.post(search_url, data=data, headers=headers, timeout=20, verify=False)
        response.raise_for_status()
        logging.info(f"✅ Formulario enviado. Status: {response.status_code}")

        # 3. DEBUG: Analizar la respuesta cruda
        debug_info = debug_html_response(response.text, cmp_number)
        logging.debug(f"🔍 DEBUG INFO: {debug_info}")

        # 4. Verificar si no hay resultados
        if "No se encontró ningún Colegiado" in response.text:
            logging.info(f"❌ No se encontró médico para CMP: {cmp_number}")
            return {
                "cmp_number": cmp_number,
                "status": "no_encontrado",
                "message": "No se encontró ningún médico con el CMP proporcionado"
            }, 404

        # 5. Analizar el HTML con BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')

        # 6. ESTRATEGIAS MÚLTIPLES para encontrar la tabla
        table = None
        table_found_by = ""

        # Estrategia 1: Buscar por atributos exactos (como en tu HTML)
        table = soup.find('table', {'border': '1', 'cellspacing': '2'})
        if table:
            table_found_by = "atributos border=1 y cellspacing=2"
            logging.info("✅ Tabla encontrada por atributos específicos")

        # Estrategia 2: Buscar cualquier tabla que contenga el CMP
        if not table:
            all_tables = soup.find_all('table')
            logging.info(f"🔍 Buscando en {len(all_tables)} tablas encontradas")
            for i, tbl in enumerate(all_tables):
                if cmp_number in tbl.get_text():
                    table = tbl
                    table_found_by = f"contenido del CMP en tabla #{i}"
                    logging.info(f"✅ Tabla encontrada por contenido del CMP")
                    break

        # Estrategia 3: Buscar por clase cabecera_tr2 directamente
        if not table:
            table_row = soup.find('tr', class_='cabecera_tr2')
            if table_row:
                table = table_row.find_parent('table')
                if table:
                    table_found_by = "clase cabecera_tr2"
                    logging.info("✅ Tabla encontrada por clase cabecera_tr2")

        if not table:
            logging.error(f"❌ No se pudo encontrar ninguna tabla con los datos")
            return {
                "cmp_number": cmp_number,
                "status": "error",
                "message": "No se encontró la tabla de resultados",
                "debug_info": debug_info  # Incluir info de debug en la respuesta
            }, 500

        # 7. Buscar la fila con los datos
        table_row = None

        # Estrategia 1: Buscar por clase
        table_row = table.find('tr', class_='cabecera_tr2')
        if table_row:
            logging.info("✅ Fila encontrada por clase cabecera_tr2")

        # Estrategia 2: Buscar cualquier fila que contenga el CMP
        if not table_row:
            for tr in table.find_all('tr'):
                if cmp_number in tr.get_text():
                    table_row = tr
                    logging.info("✅ Fila encontrada por contenido del CMP")
                    break

        if not table_row:
            logging.error("❌ No se pudo encontrar la fila con los datos")
            return {
                "cmp_number": cmp_number,
                "status": "error",
                "message": "No se encontró la fila con los datos del médico",
                "debug_info": debug_info
            }, 500

        # 8. Extraer las celdas de datos
        cells = table_row.find_all('td')
        logging.info(f"🔍 Encontradas {len(cells)} celdas en la fila")

        if len(cells) < 5:
            return {
                "cmp_number": cmp_number,
                "status": "error",
                "message": f"Estructura de tabla inesperada. Celdas encontradas: {len(cells)}",
                "debug_info": debug_info
            }, 500

        # 9. EXTRAER DATOS - Buscar el CMP en las celdas para encontrar índices correctos
        cmp_index = None
        for i, cell in enumerate(cells):
            if cell.get_text(strip=True) == cmp_number:
                cmp_index = i
                break

        # Si no encontramos el CMP exacto, usar índices por defecto
        if cmp_index is None:
            cmp_index = 1  # Índice más común según tu HTML
            logging.warning("⚠️ No se encontró el CMP exacto en celdas, usando índice por defecto")

        # Calcular índices relativos
        apellido_paterno_index = cmp_index + 1
        apellido_materno_index = cmp_index + 2
        nombres_index = cmp_index + 3

        # Verificar que los índices sean válidos
        if nombres_index >= len(cells):
            return {
                "cmp_number": cmp_number,
                "status": "error",
                "message": f"Índices de celdas inválidos para la estructura",
                "debug_info": debug_info
            }, 500

        # 10. Extraer datos
        cmp_val = cells[cmp_index].get_text(strip=True)
        apellido_paterno = cells[apellido_paterno_index].get_text(strip=True)
        apellido_materno = cells[apellido_materno_index].get_text(strip=True)
        nombres = cells[nombres_index].get_text(strip=True)

        # 11. Construir respuesta
        data = {
            "cmp_number": cmp_number,
            "cmp": cmp_val,
            "apellido_paterno": apellido_paterno,
            "apellido_materno": apellido_materno,
            "nombres": nombres,
            "nombre_completo": f"{nombres} {apellido_paterno} {apellido_materno}",
            "status": "encontrado",
            "fuente": "Colegio Médico del Perú",
            "especialidad": "Consultar en página de detalles",
            "debug": {
                "tabla_encontrada_por": table_found_by,
                "celdas_encontradas": len(cells),
                "indice_cmp": cmp_index
            }
        }

        logging.info(f"✅ DATOS REALES encontrados para CMP {cmp_number}: {data['nombre_completo']}")
        return data, 200

    except requests.exceptions.Timeout:
        logging.error("❌ Timeout en la consulta")
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
        "version": "10.0.0",
        "estado": "ACTIVA CON DEBUG",
        "uptime_seconds": round(uptime, 2),
        "tecnologia": "Requests + BeautifulSoup",
        "uso": "Validación de colegiatura médica en Perú - CON DEBUGGING",
        "endpoints": {
            "validar_medico": "GET /api/v1/medico/<cmp_number>",
            "health_check": "GET /health",
            "test_conexion": "GET /test",
            "debug_cmp": "GET /debug/<cmp_number>"
        },
        "nota": "✅ Versión con debugging completo"
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
        "version": "10.0.0",
        "tecnologia": "Requests + BeautifulSoup",
        "datos": "100% REALES del CMP",
        "uptime_seconds": round(uptime, 2),
        "timestamp": time.time(),
        "estado": "🟢 CON DEBUGGING"
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


# NUEVO ENDPOINT: Debugging completo
@app.route('/debug/<cmp_number>', methods=['GET'])
def debug_cmp(cmp_number):
    """Endpoint para debugging completo - muestra TODO el proceso"""
    try:
        session = requests.Session()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        # 1. Obtener página inicial
        response1 = session.get("https://aplicaciones.cmp.org.pe/conoce_a_tu_medico/",
                                headers=headers, verify=False, timeout=20)

        # 2. Enviar formulario
        data = {'cmp': cmp_number}
        response2 = session.post("https://aplicaciones.cmp.org.pe/conoce_a_tu_medico/datos-colegiado.php",
                                 data=data, headers=headers, verify=False, timeout=20)

        # 3. Analizar respuesta
        soup = BeautifulSoup(response2.text, 'html.parser')
        tables = soup.find_all('table')

        debug_info = {
            "cmp_number": cmp_number,
            "paso_1_status": response1.status_code,
            "paso_2_status": response2.status_code,
            "longitud_html": len(response2.text),
            "tablas_encontradas": len(tables),
            "contiene_no_results": "No se encontró ningún Colegiado" in response2.text,
            "contiene_cmp": cmp_number in response2.text,
            "contiene_table_tag": "<table" in response2.text,
            "contiene_cabecera_tr2": "cabecera_tr2" in response2.text,
            "url_final": response2.url,
            "preview_html": response2.text[:2000] + "..." if len(response2.text) > 2000 else response2.text
        }

        # Detalles de cada tabla encontrada
        for i, table in enumerate(tables):
            debug_info[f"tabla_{i}_filas"] = len(table.find_all('tr'))
            debug_info[f"tabla_{i}_contenido"] = table.get_text(strip=True)[:200]

        return jsonify(debug_info)

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500


@app.route('/status', methods=['GET'])
def status():
    """Endpoint detallado de estado"""
    uptime = time.time() - app_start_time
    return jsonify({
        "estado": "operacional",
        "version": "10.0.0",
        "uptime_segundos": round(uptime, 2),
        "timestamp": time.time(),
        "entorno": "production",
        "modo": "debugging"
    })


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    is_render = os.environ.get('RENDER') is not None

    print("=" * 70)
    print("🚀 API DE VALIDACIÓN CMP - VERSIÓN DEBUG")
    print("=" * 70)
    print(f"📍 URL: https://api-medicos-cmp.onrender.com")
    print(f"🔧 Puerto: {port}")
    print(f"🐛 Modo: DEBUGGING COMPLETO")
    print("📚 Endpoints:")
    print(f"   • GET /api/v1/medico/<cmp_number> (Principal)")
    print(f"   • GET /debug/<cmp_number> (DEBUG completo)")
    print(f"   • GET /health")
    print(f"   • GET /test")
    print("=" * 70)
    print("✅ Iniciando servicio con debugging...")
    print("=" * 70)

    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)