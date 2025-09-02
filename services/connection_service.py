from netmiko import ConnectHandler
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class ConnectionService:
    """Servicio para manejar la conexiÃ³n SSH al dispositivo"""
    
    def __init__(self, device_config: dict):
        self.device_config = device_config
        self.connection: Optional[ConnectHandler] = None
    
    def connect(self) -> ConnectHandler:
        """Establece y mantiene la conexiÃ³n SSH"""
        try:
            if self.connection is None or not self.connection.is_alive():
                logger.info("Estableciendo nueva conexiÃ³n SSH")
                self.connection = ConnectHandler(**self.device_config)
                self._initialize_connection()
            return self.connection
        except Exception as e:
            logger.error(f"Error estableciendo conexiÃ³n: {e}")
            raise
    
    def _initialize_connection(self):
        """Inicializa la conexiÃ³n con los comandos necesarios"""
        self.connection.write_channel("enable\n")
        self.connection.read_until_pattern(r"#")
        self.connection.write_channel("config\n")
        self.connection.read_until_pattern(r"\)")
    
    def execute_command(self, command: str, delay_factor: int = 1, timeout: int = 20) -> str:
        """Ejecuta un comando y retorna la salida"""
        try:
            conn = self.connect()
            return conn.send_command(
                command,
                delay_factor=delay_factor,
                expect_string=r"#",
                read_timeout=timeout
            )
        except Exception as e:
            logger.error(f"Error ejecutando comando '{command}': {e}")
            raise
    
    def enter_interface(self, tarjeta: str):
        """Entra a la interfaz GPON especificada"""
        try:
            conn = self.connect()
            conn.write_channel(f"interface gpon 0/{tarjeta}\n")
            conn.read_until_pattern(r"#")
        except Exception as e:
            logger.error(f"Error entrando a interfaz gpon 0/{tarjeta}: {e}")
            raise
    
    def disconnect(self):
        """Cierra la conexiÃ³n"""
        if self.connection and self.connection.is_alive():
            try:
                self.connection.disconnect()
                logger.info("ConexiÃ³n cerrada correctamente")
            except Exception as e:
                logger.error(f"Error cerrando conexiÃ³n: {e}")
            finally:
                self.connection = None