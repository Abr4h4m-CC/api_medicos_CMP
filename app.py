from flask import Flask, jsonify, request
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from webdriver_manager.firefox import GeckoDriverManager

import logging
import re
import os
import time

# Configurar logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)
URL_BASE = "https://aplicaciones.cmp.org.pe/conoce_a_tu_medico/"


def get_medico_data(cmp_number):
    """
    Realiza el scraping para obtener los datos del médico por su número CMP.
    """
    cmp_number = str(cmp_number).strip()

    # Configuración para Firefox en la nube
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    driver = None
    try:
        # Inicializar Firefox
        driver_path = GeckoDriverManager().install()
        service = Service(driver_path)
        driver = webdriver.Firefox(service=service, options=options)

        # Configurar timeout
        driver.set_page_load_timeout(30)
        wait = WebDriverWait(driver, 20)

        # Navegar a la página
        driver.get(URL_BASE)
        time.sleep(2)  # Pequeña pausa para estabilidad

        # 1. Ingresar CMP
        cmp_input = wait.until(
            EC.presence_of_element_located((By.NAME, "cmp"))
        )
        cmp_input.clear()
        cmp_input.send_keys(cmp_number)

        # 2. Click en Buscar
        buscar_btn = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input.btn.btn-sub[type='submit']"))
        )
        buscar_btn.click()

        # 3. Esperar resultados
        wait.until(EC.url_contains("datos-colegiado.php"))
        time.sleep(2)

        # 4. Verificar si no hay resultados
        if "No se encontró ningún Colegiado" in driver.page_source:
            return {
                "cmp_number": cmp_number,
                "status": "no_encontrado",
                "message": "No se encontró ningún médico con el CMP proporcionado"
            }, 404

        # 5. Extraer datos de la tabla
        table_row = wait.until(
            EC.presence_of_element_located((By.XPATH, "//table//tr[@class='cabecera_tr2']"))
        )
        cells = table_row.find_elements(By.TAG_NAME, "td")

        if len(cells) < 5:
            return {
                "cmp_number": cmp_number,
                "status": "error",
                "message": "Estructura de datos inesperada"
            }, 500

        # 6. Construir respuesta
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

        # 7. Buscar especialidad
        try:
            especialidad_element = driver.find_element(
                By.XPATH, "//td[contains(text(), 'Especialidad:')]"
            )
            especialidad_text = especialidad_element.text
            match = re.search(r'Especialidad:\s*(.*)', especialidad_text)
            data["especialidad"] = match.group(1).strip() if match else "No disponible"
        except Exception:
            data["especialidad"] = "No disponible"

        return data, 200

    except Exception as e:
        logging.error(f"Error en scraping: {e}")
        return {
            "cmp_number": cmp_number,
            "status": "error",
            "message": f"Error al consultar los datos: {str(e)}"
        }, 500

    finally:
        if driver:
            driver.quit()


@app.route('/')
def home():
    return jsonify({
        "message": "🚀 API de Validación CMP - Colegio Médico del Perú",
        "version": "1.0.0",
        "uso": "Para validar colegiatura médica en Perú",
        "endpoint_principal": "GET /api/v1/medico/<numero_cmp>",
        "ejemplo": "https://tu-api.onrender.com/api/v1/medico/12345"
    })


@app.route('/api/v1/medico/<cmp_number>', methods=['GET'])
def get_medico(cmp_number):
    """Endpoint principal para validar CMP"""
    # Validación del input
    if not cmp_number or not re.match(r'^\d+$', cmp_number.strip()):
        return jsonify({
            "status": "error_validacion",
            "message": "El número CMP debe contener solo dígitos numéricos"
        }), 400

    # Llamar a la función de scraping
    data, status_code = get_medico_data(cmp_number.strip())
    return jsonify(data), status_code


@app.route('/health', methods=['GET'])
def health_check():
    """Endpoint para verificar que la API está funcionando"""
    return jsonify({
        "status": "activo",
        "servicio": "API Validación CMP",
        "timestamp": time.time()
    })


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print("=" * 50)
    print("🚀 API DE VALIDACIÓN CMP INICIADA")
    print("=" * 50)
    print(f"📍 URL local: http://localhost:{port}")
    print("📚 Endpoints disponibles:")
    print(f"   • GET /api/v1/medico/<cmp_number>")
    print(f"   • GET /health")
    print(f"   • GET /")
    print("=" * 50)

    app.run(host='0.0.0.0', port=port, debug=False)