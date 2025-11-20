from flask import Flask, jsonify, request
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

import logging
import re
import os
import time

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)
URL_BASE = "https://aplicaciones.cmp.org.pe/conoce_a_tu_medico/"


def setup_driver():
    """Configura Chrome para Render"""
    options = Options()

    # Opciones esenciales para Render
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-dev-shm-usage")

    # Configuración adicional
    options.add_argument("--remote-debugging-port=9222")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    try:
        # Usar ChromeDriverManager con cache
        driver_path = ChromeDriverManager().install()
        service = Service(driver_path)
        driver = webdriver.Chrome(service=service, options=options)

        # Configurar timeouts
        driver.set_page_load_timeout(45)
        driver.implicitly_wait(15)

        return driver
    except Exception as e:
        logging.error(f"Error configurando Chrome: {e}")
        return None


def get_medico_data(cmp_number):
    """Realiza el scraping para obtener los datos del médico"""
    cmp_number = str(cmp_number).strip()
    driver = None

    try:
        driver = setup_driver()
        if not driver:
            return {
                "cmp_number": cmp_number,
                "status": "error",
                "message": "No se pudo inicializar el navegador"
            }, 500

        wait = WebDriverWait(driver, 30)

        logging.info(f"Iniciando búsqueda para CMP: {cmp_number}")

        # Navegar a la página principal
        driver.get(URL_BASE)
        time.sleep(3)

        # Buscar campo CMP
        cmp_input = wait.until(
            EC.presence_of_element_located((By.NAME, "cmp"))
        )
        cmp_input.clear()
        cmp_input.send_keys(cmp_number)

        # Click en buscar
        buscar_btn = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input.btn.btn-sub[type='submit']"))
        )
        buscar_btn.click()

        # Esperar resultados
        wait.until(EC.url_contains("datos-colegiado.php"))
        time.sleep(2)

        # Verificar si no hay resultados
        page_source = driver.page_source
        if "No se encontró ningún Colegiado" in page_source:
            return {
                "cmp_number": cmp_number,
                "status": "no_encontrado",
                "message": "No se encontró ningún médico con el CMP proporcionado"
            }, 404

        # Extraer datos de la tabla
        try:
            table_row = wait.until(
                EC.presence_of_element_located((By.XPATH, "//table//tr[@class='cabecera_tr2']"))
            )
            cells = table_row.find_elements(By.TAG_NAME, "td")

            if len(cells) < 5:
                return {
                    "cmp_number": cmp_number,
                    "status": "error",
                    "message": "Estructura de tabla inesperada"
                }, 500

            # Construir respuesta
            data = {
                "cmp_number": cmp_number,
                "cmp": cells[1].text.strip(),
                "apellido_paterno": cells[2].text.strip(),
                "apellido_materno": cells[3].text.strip(),
                "nombres": cells[4].text.strip(),
                "nombre_completo": f"{cells[4].text.strip()} {cells[2].text.strip()} {cells[3].text.strip()}",
                "status": "encontrado",
                "fuente": "Colegio Médico del Perú"
            }

            # Buscar especialidad
            try:
                especialidad_element = driver.find_element(
                    By.XPATH, "//td[contains(text(), 'Especialidad:')]"
                )
                especialidad_text = especialidad_element.text
                match = re.search(r'Especialidad:\s*(.*)', especialidad_text)
                data["especialidad"] = match.group(1).strip() if match else "No disponible"
            except Exception as e:
                logging.warning(f"No se pudo obtener especialidad: {e}")
                data["especialidad"] = "No disponible"

            logging.info(f"Datos encontrados para CMP {cmp_number}: {data['nombres']}")
            return data, 200

        except Exception as e:
            logging.error(f"Error extrayendo datos de tabla: {e}")
            return {
                "cmp_number": cmp_number,
                "status": "error",
                "message": f"Error procesando los datos: {str(e)}"
            }, 500

    except Exception as e:
        logging.error(f"Error general en scraping: {e}")
        return {
            "cmp_number": cmp_number,
            "status": "error",
            "message": f"Error al consultar el CMP: {str(e)}"
        }, 500

    finally:
        if driver:
            driver.quit()
            logging.info("Driver cerrado correctamente")


@app.route('/')
def home():
    return jsonify({
        "message": "🚀 API de Validación CMP - Colegio Médico del Perú",
        "version": "3.0.0",
        "estado": "ACTIVA",
        "navegador": "Chrome Headless",
        "uso": "Validación de colegiatura médica en Perú",
        "endpoints": {
            "validar_medico": "GET /api/v1/medico/<cmp_number>",
            "health_check": "GET /health",
            "documentacion": "GET /"
        },
        "ejemplo": "https://api-medicos-cmp.onrender.com/api/v1/medico/067890"
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
        "version": "3.0.0",
        "navegador": "Chrome",
        "timestamp": time.time()
    })


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))

    print("=" * 60)
    print("🚀 API DE VALIDACIÓN CMP - CHROME EDITION")
    print("=" * 60)
    print(f"📍 URL: https://api-medicos-cmp.onrender.com")
    print(f"🔧 Puerto: {port}")
    print(f"🌐 Navegador: Chrome Headless")
    print("📚 Endpoints:")
    print(f"   • GET /api/v1/medico/<cmp_number>")
    print(f"   • GET /health")
    print("=" * 60)

    app.run(host='0.0.0.0', port=port, debug=False)