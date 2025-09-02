class Config:
    """Configuración base"""
    SECRET_KEY = 'your-secret-key-here'
    
    # Configuración del dispositivo Huawei OLT
    DEVICE_CONFIG = {
        'device_type': 'huawei_olt',
        'ip': '10.120.6.105',
        'username': 'admin123',
        'password': 'C3NTT1X123',
    }
    
    # Configuración de timeouts y delays
    COMMAND_TIMEOUT = 20
    COMMAND_DELAY = 1