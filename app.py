from flask import Flask, jsonify, request
import requests
from bs4 import BeautifulSoup
import re
import logging
import time
import os
import urllib3

# Desactivar advertencias de SSL (solo para desarrollo)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)


def get_medico_data(cmp_number):
    """
    Obtiene los datos del médico usando requests + BeautifulSoup
    CON corrección de la estructura HTML actual del CMP
    """
    cmp_number = str(cmp_number).strip()

    try:
        # URL base y sesión
        session = requests.Session()
        base_url = "https://aplicaciones.cmp.org.pe/conoce_a_tu_medico/"

        # Headers mejorados para simular navegador
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://aplicaciones.cmp.org.pe',
            'Referer': 'https://aplicaciones.cmp.org.pe/conoce_a_tu_medico/',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin'
        }

        # 1. Obtener la página inicial (CON verify=False para SSL)
        logging.info(f"🔍 Iniciando búsqueda para CMP: {cmp_number}")
        response = session.get(base_url, headers=headers, timeout=30, verify=False)
        response.raise_for_status()

        # Verificar que estamos en la página correcta
        if "conoce_a_tu_medico" not in response.url:
            return {
                "cmp_number": cmp_number,
                "status": "error",
                "message": "No se pudo acceder a la página del CMP"
            }, 500

        # 2. Enviar el formulario de búsqueda (CON verify=False)
        data = {
            'cmp': cmp_number
        }

        search_url = "https://aplicaciones.cmp.org.pe/conoce_a_tu_medico/datos-colegiado.php"
        response = session.post(search_url, data=data, headers=headers, timeout=30, verify=False)
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

        # 5. BUSCAR LA TABLA CORRECTAMENTE - Múltiples estrategias
        table_row = None

        # Estrategia 1: Buscar por clase específica
        table_row = soup.find('tr', class_='cabecera_tr2')

        # Estrategia 2: Buscar por estilo de fondo
        if not table_row:
            table_row = soup.find('tr', style=re.compile(r'background-color'))

        # Estrategia 3: Buscar cualquier fila de tabla con muchas celdas
        if not table_row:
            for tr in soup.find_all('tr'):
                cells = tr.find_all('td')
                if len(cells) >= 5:
                    # Verificar que las celdas contengan datos coherentes
                    if any(cell.get_text(strip=True).isdigit() for cell in cells):
                        table_row = tr
                        break

        # Estrategia 4: Buscar por texto específico en las celdas
        if not table_row:
            for tr in soup.find_all('tr'):
                cells = tr.find_all('td')
                if len(cells) >= 5:
                    cell_texts = [cell.get_text(strip=True) for cell in cells]
                    # Si alguna celda contiene el número CMP buscado
                    if cmp_number in cell_texts:
                        table_row = tr
                        break

        if not table_row:
            logging.error(f"No se encontró tabla. HTML sample: {response.text[:500]}")
            return {
                "cmp_number": cmp_number,
                "status": "error",
                "message": "No se pudo encontrar los datos en la respuesta del CMP. La estructura del sitio puede haber cambiado."
            }, 500

        # 6. Extraer las celdas de datos
        cells = table_row.find_all('td')
        if len(cells) < 5:
            return {
                "cmp_number": cmp_number,
                "status": "error",
                "message": f"Estructura de tabla inesperada. Celdas encontradas: {len(cells)}"
            }, 500

        # 7. Encontrar el índice correcto del CMP (puede variar)
        cmp_index = None
        for i, cell in enumerate(cells):
            if cell.get_text(strip=True) == cmp_number:
                cmp_index = i
                break

        # Si no encontramos el CMP exacto, usar índices por defecto
        if cmp_index is None:
            cmp_index = 1  # Índice más común

        # 8. Construir respuesta con los datos - con índices flexibles
        data = {
            "cmp_number": cmp_number,
            "cmp": cells[cmp_index].get_text(strip=True),
            "apellido_paterno": cells[cmp_index + 1].get_text(strip=True) if len(
                cells) > cmp_index + 1 else "No disponible",
            "apellido_materno": cells[cmp_index + 2].get_text(strip=True) if len(
                cells) > cmp_index + 2 else "No disponible",
            "nombres": cells[cmp_index + 3].get_text(strip=True) if len(cells) > cmp_index + 3 else "No disponible",
            "status": "encontrado",
            "fuente": "Colegio Médico del Perú"
        }

        # Construir nombre completo
        data["nombre_completo"] = f"{data['nombres']} {data['apellido_paterno']} {data['apellido_materno']}"

        # 9. Buscar especialidad - métodos mejorados
        try:
            # Método 1: Buscar por texto "Especialidad:"
            especialidad_pattern = re.compile(r'Especialidad:\s*([^\n<]+)', re.IGNORECASE)
            especialidad_match = especialidad_pattern.search(response.text)

            if especialidad_match:
                data["especialidad"] = especialidad_match.group(1).strip()
            else:
                # Método 2: Buscar en elementos strong o b que contengan "Especialidad"
                especialidad_elements = soup.find_all(['strong', 'b', 'span'],
                                                      string=re.compile(r'Especialidad', re.IGNORECASE))
                for element in especialidad_elements:
                    parent_text = element.parent.get_text() if element.parent else ""
                    match = re.search(r'Especialidad[:\s]*([^\n<]+)', parent_text, re.IGNORECASE)
                    if match:
                        data["especialidad"] = match.group(1).strip()
                        break
                else:
                    data["especialidad"] = "No disponible"

        except Exception as e:
            logging.warning(f"⚠️ No se pudo obtener especialidad: {e}")
            data["especialidad"] = "No disponible"

        logging.info(f"✅ Datos encontrados para CMP {cmp_number}: {data['nombre_completo']}")
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
    return jsonify({
        "message": "🚀 API de Validación CMP - Colegio Médico del Perú",
        "version": "7.0.0",
        "estado": "ACTIVA",
        "tecnologia": "Requests + BeautifulSoup (Estructura corregida)",
        "uso": "Validación de colegiatura médica en Perú - DATOS REALES",
        "endpoints": {
            "validar_medico": "GET /api/v1/medico/<cmp_number>",
            "health_check": "GET /health",
            "test_conexion": "GET /test",
            "debug_cmp": "GET /debug/<cmp_number>"
        },
        "ejemplo": "https://api-medicos-cmp.onrender.com/api/v1/medico/067890",
        "nota": "✅ Scraping corregido para la estructura actual del CMP"
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
        "version": "7.0.0",
        "tecnologia": "Requests + BeautifulSoup",
        "ssl_verification": "desactivado",
        "timestamp": time.time(),
        "rendimiento": "Óptimo",
        "datos": "REALES del CMP"
    })


# Ruta de prueba para verificar que la API funciona
@app.route('/test', methods=['GET'])
def test_connection():
    """Endpoint para probar la conexión con el CMP"""
    try:
        response = requests.get("https://aplicaciones.cmp.org.pe/conoce_a_tu_medico/",
                                verify=False, timeout=10)
        return jsonify({
            "status": "conexion_exitosa",
            "mensaje": "Conexión al CMP establecida correctamente",
            "codigo_estado": response.status_code,
            "url": response.url
        })
    except Exception as e:
        return jsonify({
            "status": "error_conexion",
            "mensaje": f"Error conectando al CMP: {str(e)}"
        }), 500


# Ruta de debug para ver el HTML crudo
@app.route('/debug/<cmp_number>', methods=['GET'])
def debug_cmp(cmp_number):
    """Endpoint para debug - muestra el HTML crudo"""
    try:
        session = requests.Session()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        # Obtener página inicial
        response = session.get("https://aplicaciones.cmp.org.pe/conoce_a_tu_medico/",
                               headers=headers, verify=False, timeout=30)

        # Enviar formulario
        data = {'cmp': cmp_number}
        response = session.post("https://aplicaciones.cmp.org.pe/conoce_a_tu_medico/datos-colegiado.php",
                                data=data, headers=headers, verify=False, timeout=30)

        return jsonify({
            "cmp_number": cmp_number,
            "status_code": response.status_code,
            "url": response.url,
            "html_preview": response.text[:1000] + "..." if len(response.text) > 1000 else response.text,
            "contains_no_results": "No se encontró ningún Colegiado" in response.text,
            "contains_table": "cabecera_tr2" in response.text or "background-color" in response.text
        })

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))

    print("=" * 60)
    print("🚀 API DE VALIDACIÓN CMP - ESTRUCTURA CORREGIDA")
    print("=" * 60)
    print(f"📍 URL: https://api-medicos-cmp.onrender.com")
    print(f"🔧 Puerto: {port}")
    print(f"⚡ Tecnología: Requests + BeautifulSoup")
    print(f"🎯 Objetivo: Datos REALES del CMP")
    print("📚 Endpoints:")
    print(f"   • GET /api/v1/medico/<cmp_number> (Principal)")
    print(f"   • GET /health")
    print(f"   • GET /test (prueba de conexión)")
    print(f"   • GET /debug/<cmp_number> (debug)")
    print("=" * 60)
    print("✅ Iniciando servicio...")
    print("=" * 60)

    app.run(host='0.0.0.0', port=port, debug=False)