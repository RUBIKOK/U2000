import io
from flask import Blueprint, request, render_template, send_file, flash, redirect, url_for, session, jsonify
import logging
import sys
import os
import re
import traceback
import uuid

# Agregar el directorio raíz al path si es necesario
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config import Config
    from services.connection_pool import ConnectionPool  # Nueva importación
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

# Inicializar pool de conexiones (ÚNICO PARA TODA LA APLICACIÓN)
connection_pool = ConnectionPool(Config.DEVICE_CONFIG, max_idle_time=300)
excel_service = ExcelService()

# Intentar importar BoardService
board_service = None
try:
    from services.board_service import BoardService
    board_service = BoardService
    logger.info("BoardService inicializado correctamente")
except ImportError as e:
    logger.error(f"Error importando BoardService: {e}")
except Exception as e:
    logger.error(f"Error inicializando BoardService: {e}")

def get_session_id():
    """Obtiene o crea un ID único para la sesión actual"""
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
        logger.info(f"Nueva sesión creada: {session['session_id']}")
    return session['session_id']

def get_connection_for_session():
    """Obtiene una conexión específica para la sesión actual"""
    session_id = get_session_id()
    return connection_pool.get_connection(session_id)

@ont_bp.route("/")
def home():
    """Página de inicio - NO carga automáticamente las ONTs en autofind"""
    return render_template("home.html", autofind_list=[])

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
                # Usar conexión específica de la sesión
                connection_service = get_connection_for_session()
                ont_service = ONTService(connection_service)
                
                ont_collection = ont_service.obtener_onts(tarjeta, puerto)
                summary = ont_collection.get_summary()
                session['last_onts'] = ont_collection.to_dict_list()
                session['last_query'] = f"Tarjeta_{tarjeta}_Puerto_{puerto}"
                flash(f"Se encontraron {ont_collection.get_total_count()} ONTs", "success")
            except Exception as e:
                flash(f"Error al consultar ONTs: {str(e)}", "error")
                logger.error(f"Error en sesión {get_session_id()}: {e}")

    return render_template(
        "ont.html",
        onts=ont_collection.to_dict_list(),
        tarjeta=tarjeta,
        puerto=puerto,
        summary=summary
    )

@ont_bp.route("/download_tarjeta/<tarjeta>")
def download_tarjeta(tarjeta):
    """Consulta todos los puertos (0-15) de una tarjeta y descarga el Excel"""
    try:
        if not tarjeta:
            flash("Por favor ingrese una tarjeta válida", "error")
            return redirect(url_for("ont.ont_page"))

        # Usar conexión específica de la sesión
        connection_service = get_connection_for_session()
        ont_service = ONTService(connection_service)

        all_onts = ONTCollection()
        for p in range(16):  # puertos 0-15
            try:
                partial = ont_service.obtener_onts(tarjeta, str(p))
                all_onts.extend(partial)
            except Exception as e:
                logger.warning(f"Error en puerto {p} para sesión {get_session_id()}: {e}")
                continue

        if all_onts.get_total_count() == 0:
            flash("No se encontraron ONTs en la tarjeta.", "warning")
            return redirect(url_for("ont.ont_page"))

        # Generar archivo Excel
        file_stream = excel_service.generar_reporte(all_onts)
        filename = f"Reporte_Tarjeta_{tarjeta}_Puertos_0_15.xlsx"

        return send_file(
            file_stream,
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        logger.error(f"Error generando Excel para tarjeta {tarjeta} en sesión {get_session_id()}: {e}")
        flash(f"Error al generar Excel: {str(e)}", "error")
        return redirect(url_for("ont.ont_page"))

@ont_bp.route("/authorize_ont/<sn>")
def authorize_ont(sn):
    """Ruta para autorizar una ONT desde autofind"""
    try:
        flash(f"Funcionalidad de autorización para ONT {sn} - En desarrollo", "info")
        return redirect(url_for('ont.home'))
        
    except Exception as e:
        logger.error(f"Error autorizando ONT {sn} en sesión {get_session_id()}: {e}")
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
            ont = ONT(
                id=ont_data['id'],
                tarjeta=ont_data['tarjeta'],
                puerto=ont_data['puerto'],
                ont_rx=ont_data['ont_rx'],
                olt_rx=ont_data['olt_rx'],
                temperature=ont_data['temperature'],
                distance=ont_data['distance'],
                estado=ont_data['estado'],
                last_down_time=ont_data['last_down_time'],
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
        logger.error(f"Error generando Excel en sesión {get_session_id()}: {e}")
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
        logger.info(f"=== API Request: Tarjeta {tarjeta} en sesión {get_session_id()} ===")

        if board_service is None:
            logger.error("BoardService no está disponible")
            return jsonify({
                "error": "Servicio de tarjetas no disponible. Verifique la configuración del servidor."
            }), 500

        # Validar formato de tarjeta
        if not re.match(r'^(1[0-7]|[1-9])$', tarjeta):
            logger.warning(f"Formato de tarjeta inválido: {tarjeta}")
            return jsonify({
                "error": "Formato de tarjeta inválido. Solo se permiten números entre 1 y 15"
            }), 400

        # Usar conexión específica de la sesión
        connection_service = get_connection_for_session()
        board_service_instance = BoardService(connection_service)
        
        board_data = board_service_instance.obtener_puertos_tarjeta(tarjeta)
        logger.info(f"Consulta exitosa para tarjeta {tarjeta} en sesión {get_session_id()}")
        return jsonify(board_data)

    except Exception as e:
        logger.error(f"Error en API /api/board/{tarjeta} en sesión {get_session_id()}: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"error": f"Error interno del servidor: {str(e)}"}), 500

@ont_bp.route("/api/test")
def test_api():
    """Endpoint de prueba para verificar que la API funciona"""
    session_id = get_session_id()
    active_connections = connection_pool.get_active_connections_count()
    
    return jsonify({
        "status": "ok", 
        "message": "API funcionando correctamente",
        "session_id": session_id,
        "active_connections": active_connections,
        "board_service_available": board_service is not None
    })

@ont_bp.route("/api/autofind/refresh")
def refresh_autofind():
    """API endpoint para refrescar datos de autofind"""
    try:
        logger.info(f"Iniciando consulta de autofind ONTs en sesión {get_session_id()}")
        
        # Usar conexión específica de la sesión
        connection_service = get_connection_for_session()
        ont_service = ONTService(connection_service)
        
        autofind_list = ont_service.obtener_autofind_onts()
        logger.info(f"Se obtuvieron {len(autofind_list)} ONTs en autofind para sesión {get_session_id()}")
        
        return jsonify({
            "status": "success",
            "count": len(autofind_list),
            "data": autofind_list,
            "message": f"Se encontraron {len(autofind_list)} ONUs detectadas automáticamente"
        })
    except Exception as e:
        logger.error(f"Error refrescando autofind en sesión {get_session_id()}: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@ont_bp.route("/api/session/disconnect")
def disconnect_session():
    """Endpoint para desconectar manualmente la sesión actual"""
    try:
        session_id = get_session_id()
        connection_pool.disconnect_session(session_id)
        # Limpiar el session_id para forzar una nueva conexión
        session.pop('session_id', None)
        
        return jsonify({
            "status": "success",
            "message": f"Sesión {session_id} desconectada correctamente"
        })
    except Exception as e:
        logger.error(f"Error desconectando sesión: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@ont_bp.route("/api/connections/status")
def connections_status():
    """Endpoint para ver el estado de las conexiones"""
    try:
        return jsonify({
            "active_connections": connection_pool.get_active_connections_count(),
            "current_session": get_session_id()
        })
    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500

@ont_bp.errorhandler(Exception)
def handle_error(error):
    """Manejo global de errores"""
    session_id = session.get('session_id', 'unknown')
    logger.error(f"Error no manejado en sesión {session_id}: {error}")
    logger.error(f"Traceback: {traceback.format_exc()}")
    
    # Si es una petición AJAX (API), devolver JSON
    if request.path.startswith('/api/'):
        return jsonify({"error": "Error interno del servidor"}), 500
    
    # Si es una petición normal, mostrar mensaje flash
    flash("Ha ocurrido un error inesperado. Por favor intente nuevamente.", "error")
    return redirect(url_for('ont.home'))
