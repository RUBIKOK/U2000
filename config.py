import os

class Config:
    """Configuración de la aplicación"""
    
    # Configuración de la aplicación
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'tu-clave-secreta-muy-segura-aqui'
    APP_VERSION = "1.2.0"
    
    # Configuración del dispositivo OLT
    DEVICE_CONFIG = {
        'device_type': 'huawei_olt',
        'ip': os.environ.get('OLT_IP') or '10.120.6.105',  # IP de tu OLT
        'username': os.environ.get('OLT_USERNAME') or 'admin123',
        'password': os.environ.get('OLT_PASSWORD') or 'C3NTT1X123',
        'port': int(os.environ.get('OLT_PORT', 22)),
        'timeout': 30,
        'session_timeout': 300,
        'blocking_timeout': 20,
        'banner_timeout': 15,
        'conn_timeout': 10,
        'auth_timeout': 10,
        'fast_cli': False,
        'global_delay_factor': 2,
        'secret': os.environ.get('OLT_ENABLE_SECRET') or '',  # Si requiere secret para enable
    }
    
    # Configuración del pool de conexiones
    CONNECTION_POOL_CONFIG = {
        'max_idle_time': int(os.environ.get('MAX_IDLE_TIME', 300)),  # 5 minutos
        'cleanup_interval': int(os.environ.get('CLEANUP_INTERVAL', 60)),  # 1 minuto
        'max_connections': int(os.environ.get('MAX_CONNECTIONS', 50)),  # Máximo 50 conexiones
    }
    
    # Configuración de logging
    LOGGING_CONFIG = {
        'level': os.environ.get('LOG_LEVEL', 'INFO'),
        'format': '%(asctime)s - %(name)s - %(levelname)s - [Session: %(session_id)s] - %(message)s',
        'file': os.environ.get('LOG_FILE', 'olt_monitor.log'),
        'max_size': int(os.environ.get('LOG_MAX_SIZE', 10485760)),  # 10MB
        'backup_count': int(os.environ.get('LOG_BACKUP_COUNT', 5))
    }
    
    # Configuración de Flask
    FLASK_CONFIG = {
        'host': os.environ.get('FLASK_HOST', '0.0.0.0'),
        'port': int(os.environ.get('FLASK_PORT', 5002)),
        'debug': os.environ.get('FLASK_DEBUG', 'False').lower() == 'true',
        'threaded': True,
        'use_reloader': False  # Evitar problemas con hilos
    }
    
    @classmethod
    def validate_config(cls):
        """Valida la configuración"""
        required_fields = ['ip', 'username', 'password']
        missing_fields = []
        
        for field in required_fields:
            if not cls.DEVICE_CONFIG.get(field):
                missing_fields.append(field)
        
        if missing_fields:
            raise ValueError(f"Configuración incompleta. Faltan campos: {', '.join(missing_fields)}")
        
        return True
