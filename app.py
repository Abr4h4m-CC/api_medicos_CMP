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

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)


def get_medico_data(cmp_number):
    """
    Obtiene los datos del médico usando requests + BeautifulSoup
    CON la estructura EXACTA del CMP que acabas de mostrar
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
        response = session.get(base_url, headers=headers, timeout=30, verify=False)
        response.raise_for_status()

        # 2. Enviar el formulario de búsqueda
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

        # 5. BUSCAR LA TABLA EXACTA que mostraste en el HTML
        table = soup.find('table', {'width': '100%', 'border': '1', 'cellspacing': '2'})
        if not table:
            return {
                "cmp_number": cmp_number,
                "status": "error",
                "message": "No se encontró la tabla de resultados"
            }, 500

        # 6. Buscar la fila con clase 'cabecera_tr2' (EXACTA como en tu HTML)
        table_row = table.find('tr', class_='cabecera_tr2')
        if not table_row:
            return {
                "cmp_number": cmp_number,
                "status": "error",
                "message": "No se encontró la fila con los datos del médico"
            }, 500

        # 7. Extraer las celdas de datos (EXACTA estructura de tu HTML)
        cells = table_row.find_all('td')
        if len(cells) < 5:
            return {
                "cmp_number": cmp_number,
                "status": "error",
                "message": f"Estructura de tabla inesperada. Celdas encontradas: {len(cells)}"
            }, 500

        # 8. EXTRAER DATOS CON LA ESTRUCTURA EXACTA de tu HTML:
        # [0] = Detalle (enlace)
        # [1] = CMP
        # [2] = Apellido Paterno
        # [3] = Apellido Materno
        # [4] = Nombres

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
            "fuente": "Colegio Médico del Perú"
        }

        # 10. OBTENER ESPECIALIDAD - haciendo clic en el enlace de detalle
        try:
            # Buscar el enlace de detalles
            detail_link = cells[0].find('a')
            if detail_link and detail_link.get('href'):
                detail_url = "https://aplicaciones.cmp.org.pe/conoce_a_tu_medico/" + detail_link['href']

                # Hacer solicitud a la página de detalles
                detail_response = session.get(detail_url, headers=headers, timeout=30, verify=False)
                detail_response.raise_for_status()

                detail_soup = BeautifulSoup(detail_response.text, 'html.parser')

                # Buscar especialidad en la página de detalles
                # Puede estar en diferentes lugares, buscar patrones comunes
                especialidad_text = detail_soup.get_text()

                # Patrón 1: Buscar "Especialidad:" en el texto
                especialidad_match = re.search(r'Especialidad[:\s]*([^\n\r<]+)', especialidad_text, re.IGNORECASE)
                if especialidad_match:
                    data["especialidad"] = especialidad_match.group(1).strip()
                else:
                    # Patrón 2: Buscar en elementos específicos
                    especialidad_elem = detail_soup.find(['strong', 'b', 'td'],
                                                         string=re.compile(r'Especialidad', re.IGNORECASE))
                    if especialidad_elem:
                        parent_text = especialidad_elem.parent.get_text() if especialidad_elem.parent else ""
                        match = re.search(r'Especialidad[:\s]*([^\n\r<]+)', parent_text, re.IGNORECASE)
                        if match:
                            data["especialidad"] = match.group(1).strip()
                        else:
                            data["especialidad"] = "No disponible"
                    else:
                        data["especialidad"] = "No disponible"
            else:
                data["especialidad"] = "No disponible"

        except Exception as e:
            logging.warning(f"⚠️ No se pudo obtener especialidad: {e}")
            data["especialidad"] = "No disponible"

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
    return jsonify({
        "message": "🚀 API de Validación CMP - Colegio Médico del Perú",
        "version": "8.0.0",
        "estado": "ACTIVA",
        "tecnologia": "Requests + BeautifulSoup (Estructura EXACTA del CMP)",
        "uso": "Validación de colegiatura médica en Perú - DATOS 100% REALES",
        "endpoints": {
            "validar_medico": "GET /api/v1/medico/<cmp_number>",
            "health_check": "GET /health",
            "test_conexion": "GET /test"
        },
        "ejemplo_funciona": "https://api-medicos-cmp.onrender.com/api/v1/medico/067890",
        "nota": "✅ Scraping corregido con la estructura EXACTA del CMP"
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
        "version": "8.0.0",
        "tecnologia": "Requests + BeautifulSoup",
        "datos": "100% REALES del CMP",
        "timestamp": time.time(),
        "ejemplo_funciona": "CMP 067890 - NIELS JOSLIN POMAYAY YARANGA"
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
            "codigo_estado": response.status_code
        })
    except Exception as e:
        return jsonify({
            "status": "error_conexion",
            "mensaje": f"Error conectando al CMP: {str(e)}"
        }), 500


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))

    print("=" * 60)
    print("🚀 API DE VALIDACIÓN CMP - ESTRUCTURA EXACTA DEL CMP")
    print("=" * 60)
    print(f"📍 URL: https://api-medicos-cmp.onrender.com")
    print(f"🔧 Puerto: {port}")
    print(f"🎯 DATOS: 100% REALES del CMP")
    print(f"✅ EJEMPLO: CMP 067890 - NIELS JOSLIN POMAYAY YARANGA")
    print("📚 Endpoints:")
    print(f"   • GET /api/v1/medico/<cmp_number>")
    print(f"   • GET /health")
    print(f"   • GET /test")
    print("=" * 60)
    print("✅ Iniciando servicio...")
    print("=" * 60)

    app.run(host='0.0.0.0', port=port, debug=False)