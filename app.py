from flask import Flask, jsonify, request
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import logging
import time
import os
import re

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)
app_start_time = time.time()


def setup_chrome_driver():
    """Configura Chrome para Render con opciones específicas"""
    chrome_options = Options()

    # Opciones esenciales para Render
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-images")  # Más rápido

    # Configuración adicional para evitar detección
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    # En Render, Chrome ya está instalado, usar la ruta por defecto
    chrome_options.binary_location = "/usr/bin/google-chrome"

    try:
        # Usar ChromeDriverManager para manejar el driver
        from webdriver_manager.chrome import ChromeDriverManager
        from webdriver_manager.core.os_manager import ChromeType

        driver_path = ChromeDriverManager(chrome_type=ChromeType.GOOGLE).install()
        service = Service(driver_path)

        driver = webdriver.Chrome(service=service, options=chrome_options)

        # Ejecutar script para evitar detección
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        driver.set_page_load_timeout(30)
        return driver

    except Exception as e:
        logging.error(f"Error configurando Chrome: {e}")
        return None


def get_medico_data_selenium(cmp_number):
    """Obtiene datos usando Selenium con Chrome real"""
    cmp_number = str(cmp_number).strip()
    driver = None

    try:
        driver = setup_chrome_driver()
        if not driver:
            return {
                "cmp_number": cmp_number,
                "status": "error",
                "message": "No se pudo inicializar el navegador"
            }, 500

        wait = WebDriverWait(driver, 25)
        url = "https://aplicaciones.cmp.org.pe/conoce_a_tu_medico/"

        logging.info(f"🚀 Navegando a: {url}")
        driver.get(url)
        time.sleep(3)  # Esperar carga inicial

        # 1. Buscar campo CMP
        logging.info("🔍 Buscando campo CMP...")
        cmp_input = wait.until(
            EC.presence_of_element_located((By.NAME, "cmp"))
        )
        cmp_input.clear()
        cmp_input.send_keys(cmp_number)
        logging.info(f"✅ CMP {cmp_number} ingresado")

        # 2. Hacer clic en Buscar
        logging.info("🔍 Buscando botón Buscar...")
        buscar_btn = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input.btn.btn-sub[type='submit']"))
        )
        buscar_btn.click()
        logging.info("✅ Clic en Buscar realizado")

        # 3. Esperar resultados - verificar que no sea redirección
        time.sleep(5)  # Esperar procesamiento

        current_url = driver.current_url
        logging.info(f"🌐 URL actual: {current_url}")

        if "index.php" in current_url:
            return {
                "cmp_number": cmp_number,
                "status": "error",
                "message": "El CMP está bloqueado por reCAPTCHA. Intente con Selenium localmente."
            }, 500

        # 4. Buscar tabla de resultados
        logging.info("🔍 Buscando tabla de resultados...")
        try:
            table = wait.until(
                EC.presence_of_element_located((By.XPATH, "//table[@border='1' and @cellspacing='2']"))
            )
        except:
            # Intentar encontrar cualquier tabla con el CMP
            tables = driver.find_elements(By.TAG_NAME, "table")
            table = None
            for tbl in tables:
                if cmp_number in tbl.text:
                    table = tbl
                    break

            if not table:
                if "No se encontró ningún Colegiado" in driver.page_source:
                    return {
                        "cmp_number": cmp_number,
                        "status": "no_encontrado",
                        "message": "No se encontró ningún médico con el CMP proporcionado"
                    }, 404
                else:
                    return {
                        "cmp_number": cmp_number,
                        "status": "error",
                        "message": "No se encontró la tabla de resultados"
                    }, 500

        # 5. Buscar fila con datos
        logging.info("🔍 Buscando fila con datos...")
        try:
            table_row = table.find_element(By.XPATH, ".//tr[contains(@class, 'cabecera_tr2')]")
        except:
            # Buscar cualquier fila que contenga el CMP
            rows = table.find_elements(By.TAG_NAME, "tr")
            table_row = None
            for row in rows:
                if cmp_number in row.text:
                    table_row = row
                    break

            if not table_row:
                return {
                    "cmp_number": cmp_number,
                    "status": "error",
                    "message": "No se encontró la fila con los datos del médico"
                }, 500

        # 6. Extraer celdas
        cells = table_row.find_elements(By.TAG_NAME, "td")
        logging.info(f"📊 Celdas encontradas: {len(cells)}")

        if len(cells) < 5:
            return {
                "cmp_number": cmp_number,
                "status": "error",
                "message": f"Estructura de tabla inesperada. Celdas: {len(cells)}"
            }, 500

        # 7. Extraer datos (índices según tu HTML)
        cmp_val = cells[1].text.strip()
        apellido_paterno = cells[2].text.strip()
        apellido_materno = cells[3].text.strip()
        nombres = cells[4].text.strip()

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

        # 8. Intentar obtener especialidad desde página de detalles
        try:
            detail_link = cells[0].find_element(By.TAG_NAME, "a")
            if detail_link:
                detail_url = detail_link.get_attribute("href")
                if detail_url:
                    # Navegar a página de detalles
                    driver.get(detail_url)
                    time.sleep(2)

                    # Buscar especialidad en la página de detalles
                    page_text = driver.page_source
                    especialidad_match = re.search(r'Especialidad[:\s]*([^\n<]+)', page_text, re.IGNORECASE)
                    if especialidad_match:
                        data["especialidad"] = especialidad_match.group(1).strip()
                    else:
                        data["especialidad"] = "No disponible"
        except Exception as e:
            logging.warning(f"⚠️ No se pudo obtener especialidad: {e}")
            data["especialidad"] = "No disponible"

        logging.info(f"✅ DATOS ENCONTRADOS: {data['nombre_completo']}")
        return data, 200

    except Exception as e:
        logging.error(f"❌ Error en Selenium: {e}")
        return {
            "cmp_number": cmp_number,
            "status": "error",
            "message": f"Error al consultar: {str(e)}"
        }, 500

    finally:
        if driver:
            driver.quit()
            logging.info("🔚 Navegador cerrado")


@app.route('/')
def home():
    uptime = time.time() - app_start_time
    return jsonify({
        "message": "🚀 API de Validación CMP - Colegio Médico del Perú",
        "version": "11.0.0",
        "estado": "ACTIVA CON SELENIUM",
        "uptime_seconds": round(uptime, 2),
        "tecnologia": "Selenium + Chrome Real",
        "uso": "Validación de colegiatura médica en Perú - DATOS 100% REALES",
        "endpoints": {
            "validar_medico": "GET /api/v1/medico/<cmp_number>",
            "health_check": "GET /health",
            "status": "GET /status"
        },
        "nota": "✅ Usando Selenium con Chrome real para evitar reCAPTCHA"
    })


@app.route('/api/v1/medico/<cmp_number>', methods=['GET'])
def get_medico(cmp_number):
    """Endpoint principal para validar CMP"""
    if not cmp_number or not re.match(r'^\d+$', cmp_number.strip()):
        return jsonify({
            "status": "error_validacion",
            "message": "El número CMP debe contener solo dígitos numéricos"
        }), 400

    data, status_code = get_medico_data_selenium(cmp_number.strip())
    return jsonify(data), status_code


@app.route('/health', methods=['GET'])
def health_check():
    """Endpoint de salud del servicio"""
    uptime = time.time() - app_start_time
    return jsonify({
        "status": "activo",
        "servicio": "API Validación CMP",
        "version": "11.0.0",
        "tecnologia": "Selenium + Chrome",
        "datos": "100% REALES del CMP",
        "uptime_seconds": round(uptime, 2),
        "timestamp": time.time(),
        "estado": "🟢 CON SELENIUM"
    })


@app.route('/status', methods=['GET'])
def status():
    """Endpoint detallado de estado"""
    uptime = time.time() - app_start_time
    return jsonify({
        "estado": "operacional",
        "version": "11.0.0",
        "uptime_segundos": round(uptime, 2),
        "timestamp": time.time(),
        "entorno": "production",
        "tecnologia": "Selenium WebDriver"
    })


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))

    print("=" * 70)
    print("🚀 API DE VALIDACIÓN CMP - SELENIUM CHROME")
    print("=" * 70)
    print(f"📍 URL: https://api-medicos-cmp.onrender.com")
    print(f"🔧 Puerto: {port}")
    print(f"🌐 Navegador: Chrome Real con Selenium")
    print(f"🎯 OBJETIVO: Evitar reCAPTCHA y obtener datos REALES")
    print("📚 Endpoints:")
    print(f"   • GET /api/v1/medico/<cmp_number>")
    print(f"   • GET /health")
    print(f"   • GET /status")
    print("=" * 70)
    print("✅ Iniciando servicio con Selenium...")
    print("=" * 70)

    app.run(host='0.0.0.0', port=port, debug=False)