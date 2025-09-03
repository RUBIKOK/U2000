from flask import Blueprint, request, render_template, send_file, flash, redirect, url_for, session, jsonify
import logging
import sys
import os
import re
import traceback

# Agregar el directorio raíz al path si es necesario
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config import Config
    from services.connection_service import ConnectionService
    from services.ont_service import ONTService
    from services.excel_service import ExcelService
    from models.ont_model import ONT, ONTCollection
except ImportError as e:
    print(f"Error de importación básica: {e}")
    print("Verificar que todos los archivos básicos estén en su lugar correcto")
    sys.exit(1)

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Crear blueprint
ont_bp = Blueprint('ont', __name__)

# Inicializar servicios básicos
connection_service = ConnectionService(Config.DEVICE_CONFIG)
ont_service = ONTService(connection_service)
excel_service = ExcelService()

# Intentar importar BoardService
board_service = None
try:
    from services.board_service import BoardService
    board_service = BoardService(connection_service)
    logger.info("BoardService inicializado correctamente")
except ImportError as e:
    logger.error(f"Error importando BoardService: {e}")
except Exception as e:
    logger.error(f"Error inicializando BoardService: {e}")

@ont_bp.route("/")
def home():
    """Página de inicio con información de autofind ONTs"""
    autofind_list = []
    
    try:
        # Obtener ONTs en autofind
        autofind_list = ont_service.obtener_autofind_onts()
        logger.info(f"Se obtuvieron {len(autofind_list)} ONTs en autofind")
        
        if autofind_list:
            flash(f"Se encontraron {len(autofind_list)} ONUs detectadas automáticamente", "info")
        
    except Exception as e:
        logger.error(f"Error obteniendo autofind ONTs: {e}")
        flash("Error al obtener ONTs detectadas automáticamente", "warning")
    
    return render_template("home.html", autofind_list=autofind_list)

@ont_bp.route("/onts", methods=["GET", "POST"])
def ont_page():
    ont_collection = ONTCollection()
    tarjeta = ""
    puerto = ""
    summary = {"total_onts": 0, "online_onts": 0, "critical_onts": 0}

    if request.method == "POST":
        tarjeta = request.form.get("tarjeta", "4").strip()
        puerto = request.form.get("puerto", "0").strip()
        if not tarjeta or not puerto:
            flash("Por favor ingrese tarjeta y puerto válidos", "error")
        else:
            try:
                ont_collection = ont_service.obtener_onts(tarjeta, puerto)
                summary = ont_collection.get_summary()
                session['last_onts'] = ont_collection.to_dict_list()
                session['last_query'] = f"Tarjeta_{tarjeta}_Puerto_{puerto}"
                flash(f"Se encontraron {ont_collection.get_total_count()} ONTs", "success")
            except Exception as e:
                flash(f"Error al consultar ONTs: {str(e)}", "error")

    return render_template(
        "ont.html",
        onts=ont_collection.to_dict_list(),
        tarjeta=tarjeta,
        puerto=puerto,
        summary=summary
    )

@ont_bp.route("/authorize_ont/<sn>")
def authorize_ont(sn):
    """Ruta para autorizar una ONT desde autofind"""
    try:
        # Aquí iría la lógica para autorizar la ONT
        # Por ahora solo mostramos un mensaje
        flash(f"Funcionalidad de autorización para ONT {sn} - En desarrollo", "info")
        return redirect(url_for('ont.home'))
        
    except Exception as e:
        logger.error(f"Error autorizando ONT {sn}: {e}")
        flash(f"Error al autorizar ONT: {str(e)}", "error")
        return redirect(url_for('ont.home'))

@ont_bp.route("/download_excel")
def download_excel():
    """Controlador para descargar Excel"""
    try:
        # Obtener datos de la sesión
        last_onts_data = session.get('last_onts', [])
        if not last_onts_data:
            flash("No hay datos para exportar. Realice una consulta primero.", "error")
            return redirect(url_for('ont.ont_page'))
        
        # Recrear colección desde los datos de sesión
        ont_collection = ONTCollection()
        for ont_data in last_onts_data:
            # Crear ONT desde diccionario (necesitamos mapear algunos campos)
            from models.ont_model import ONT
            ont = ONT(
                id=ont_data['id'],
                tarjeta=ont_data['tarjeta'],
                puerto=ont_data['puerto'],
                ont_rx=ont_data['ont_rx'],
                olt_rx=ont_data['olt_rx'],
                temperature=ont_data['temperature'],
                distance=ont_data['distance'],
                estado=ont_data['estado'],
                last_down_cause=ont_data['last_down_cause'],
                descripcion=ont_data['descripcion']
            )
            ont_collection.add_ont(ont)
        
        # Generar archivo
        file_stream = excel_service.generar_reporte(ont_collection)
        
        # Nombre del archivo con información de la consulta
        query_info = session.get('last_query', 'ONTs')
        filename = f"Reporte_{query_info}.xlsx"
        
        return send_file(
            file_stream,
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    
    except Exception as e:
        logger.error(f"Error generando Excel: {e}")
        flash(f"Error al generar el archivo Excel: {str(e)}", "error")
        return redirect(url_for('ont.ont_page'))

@ont_bp.route("/monitor")
def monitor():
    """Vista del monitor de puertos PON"""
    return render_template("monitor.html")

@ont_bp.route("/api/board/<tarjeta>")
def get_board_data(tarjeta):
    """API endpoint para obtener datos de una tarjeta específica"""
    try:
        logger.info(f"=== API Request: Tarjeta {tarjeta} ===")

        if board_service is None:
            logger.error("BoardService no está disponible")
            return jsonify({
                "error": "Servicio de tarjetas no disponible. Verifique la configuración del servidor."
            }), 500

        # Validar formato de tarjeta (ejemplo: "0/2")
        if not re.match(r'^(1[0-7]|[1-9])$', tarjeta):
            logger.warning(f"Formato de tarjeta inválido: {tarjeta}")
            return jsonify({
                "error": "Formato de tarjeta inválido. Solo se permiten números entre 1 y 15"
            }), 400

        board_data = board_service.obtener_puertos_tarjeta(tarjeta)
        logger.info(f"Consulta exitosa para tarjeta {tarjeta}")
        return jsonify(board_data)

    except Exception as e:
        logger.error(f"Error en API /api/board/{tarjeta}: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"error": f"Error interno del servidor: {str(e)}"}), 500

@ont_bp.route("/api/test")
def test_api():
    """Endpoint de prueba para verificar que la API funciona"""
    return jsonify({
        "status": "ok", 
        "message": "API funcionando correctamente",
        "board_service_available": board_service is not None
    })

@ont_bp.route("/api/autofind/refresh")
def refresh_autofind():
    """API endpoint para refrescar datos de autofind"""
    try:
        autofind_list = ont_service.obtener_autofind_onts()
        return jsonify({
            "status": "success",
            "count": len(autofind_list),
            "data": autofind_list
        })
    except Exception as e:
        logger.error(f"Error refrescando autofind: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@ont_bp.errorhandler(Exception)
def handle_error(error):
    """Manejo global de errores"""
    logger.error(f"Error no manejado: {error}")
    logger.error(f"Traceback: {traceback.format_exc()}")
    
    # Si es una petición AJAX (API), devolver JSON
    if request.path.startswith('/api/'):
        return jsonify({"error": "Error interno del servidor"}), 500
    
    # Si es una petición normal, mostrar mensaje flash
    flash("Ha ocurrido un error inesperado. Por favor intente nuevamente.", "error")
    return redirect(url_for('ont.home'))