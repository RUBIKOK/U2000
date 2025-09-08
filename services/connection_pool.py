import threading
import time
import uuid
from typing import Dict, Optional
from netmiko import ConnectHandler
import logging

logger = logging.getLogger(__name__)

class ConnectionPool:
    """Pool de conexiones SSH independientes por sesión"""
    
    def __init__(self, device_config: dict, max_idle_time: int = 300):
        self.device_config = device_config
        self.max_idle_time = max_idle_time  # 5 minutos por defecto
        self.connections: Dict[str, Dict] = {}
        self.lock = threading.Lock()
        
        # Hilo de limpieza de conexiones inactivas
        self.cleanup_thread = threading.Thread(target=self._cleanup_inactive_connections, daemon=True)
        self.cleanup_thread.start()
    
    def get_connection(self, session_id: str) -> 'SessionConnection':
        """Obtiene o crea una conexión para la sesión especificada"""
        with self.lock:
            if session_id not in self.connections:
                logger.info(f"Creando nueva conexión para sesión {session_id}")
                self.connections[session_id] = {
                    'connection': None,
                    'last_used': time.time(),
                    'current_context': 'global'
                }
            else:
                # Actualizar último uso
                self.connections[session_id]['last_used'] = time.time()
        
        return SessionConnection(self, session_id)
    
    def _get_ssh_connection(self, session_id: str) -> ConnectHandler:
        """Obtiene la conexión SSH real, creándola si es necesario"""
        session_data = self.connections[session_id]
        
        if session_data['connection'] is None or not session_data['connection'].is_alive():
            logger.info(f"Estableciendo nueva conexión SSH para sesión {session_id}")
            session_data['connection'] = ConnectHandler(**self.device_config)
            self._initialize_connection(session_data['connection'])
            session_data['current_context'] = 'config'
        
        return session_data['connection']
    
    def _initialize_connection(self, connection: ConnectHandler):
        """Inicializa la conexión con los comandos necesarios"""
        connection.write_channel("enable\n")
        connection.read_until_pattern(r"#")
        connection.write_channel("config\n")
        connection.read_until_pattern(r"\)")
    
    def disconnect_session(self, session_id: str):
        """Desconecta una sesión específica"""
        with self.lock:
            if session_id in self.connections:
                session_data = self.connections[session_id]
                if session_data['connection'] and session_data['connection'].is_alive():
                    try:
                        # Salir de cualquier interfaz antes de desconectar
                        if session_data['current_context'].startswith("interface"):
                            session_data['connection'].write_channel("quit\n")
                            session_data['connection'].read_until_pattern(r"\)#")
                        
                        session_data['connection'].disconnect()
                        logger.info(f"Conexión cerrada para sesión {session_id}")
                    except Exception as e:
                        logger.error(f"Error cerrando conexión para sesión {session_id}: {e}")
                
                del self.connections[session_id]
    
    def _cleanup_inactive_connections(self):
        """Limpia conexiones inactivas en segundo plano"""
        while True:
            try:
                current_time = time.time()
                inactive_sessions = []
                
                with self.lock:
                    for session_id, session_data in self.connections.items():
                        if current_time - session_data['last_used'] > self.max_idle_time:
                            inactive_sessions.append(session_id)
                
                # Desconectar sesiones inactivas fuera del lock
                for session_id in inactive_sessions:
                    logger.info(f"Limpiando conexión inactiva para sesión {session_id}")
                    self.disconnect_session(session_id)
                
                time.sleep(60)  # Verificar cada minuto
                
            except Exception as e:
                logger.error(f"Error en limpieza de conexiones: {e}")
                time.sleep(60)
    
    def get_active_connections_count(self) -> int:
        """Retorna el número de conexiones activas"""
        with self.lock:
            return len(self.connections)
    
    def get_session_context(self, session_id: str) -> str:
        """Retorna el contexto actual de una sesión"""
        with self.lock:
            if session_id in self.connections:
                return self.connections[session_id]['current_context']
        return 'global'
    
    def set_session_context(self, session_id: str, context: str):
        """Establece el contexto de una sesión"""
        with self.lock:
            if session_id in self.connections:
                self.connections[session_id]['current_context'] = context


class SessionConnection:
    """Wrapper para una conexión específica de sesión"""
    
    def __init__(self, pool: ConnectionPool, session_id: str):
        self.pool = pool
        self.session_id = session_id
    
    @property
    def current_context(self) -> str:
        return self.pool.get_session_context(self.session_id)
    
    def connect(self) -> ConnectHandler:
        """Establece y mantiene la conexión SSH"""
        return self.pool._get_ssh_connection(self.session_id)
    
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
            logger.error(f"Error ejecutando comando '{command}' en sesión {self.session_id}: {e}")
            raise
    
    def execute_global_command(self, command: str, delay_factor: int = 1, timeout: int = 20) -> str:
        """Ejecuta un comando en contexto global"""
        try:
            conn = self.connect()
            
            # Si estamos en una interfaz específica, salir al modo config global
            if self.current_context.startswith("interface"):
                logger.info(f"Saliendo del contexto {self.current_context} al modo config global")
                conn.write_channel("quit\n")
                conn.read_until_pattern(r"\)#")
                self.pool.set_session_context(self.session_id, "config")
            
            # Ejecutar el comando
            result = conn.send_command(
                command,
                delay_factor=delay_factor,
                expect_string=r"#",
                read_timeout=timeout
            )
            
            return result
        except Exception as e:
            logger.error(f"Error ejecutando comando global '{command}' en sesión {self.session_id}: {e}")
            raise
    
    def enter_interface(self, tarjeta: str):
        """Entra a la interfaz GPON especificada"""
        try:
            conn = self.connect()
            
            # Si ya estamos en una interfaz diferente, salir primero
            interface_name = f"gpon-0/{tarjeta}"
            if (self.current_context.startswith("interface") and 
                self.current_context != f"interface-{interface_name}"):
                logger.info(f"Saliendo del contexto actual: {self.current_context}")
                conn.write_channel("quit\n")
                conn.read_until_pattern(r"\)#")
                self.pool.set_session_context(self.session_id, "config")
            
            # Entrar a la interfaz específica
            if self.current_context != f"interface-{interface_name}":
                logger.info(f"Entrando a interfaz gpon 0/{tarjeta} en sesión {self.session_id}")
                conn.write_channel(f"interface gpon 0/{tarjeta}\n")
                conn.read_until_pattern(r"#")
                self.pool.set_session_context(self.session_id, f"interface-{interface_name}")
                
        except Exception as e:
            logger.error(f"Error entrando a interfaz gpon 0/{tarjeta} en sesión {self.session_id}: {e}")
            raise
    
    def exit_interface(self):
        """Sale de la interfaz actual y vuelve al modo config"""
        try:
            if self.current_context.startswith("interface"):
                conn = self.connect()
                logger.info(f"Saliendo del contexto {self.current_context} en sesión {self.session_id}")
                conn.write_channel("quit\n")
                conn.read_until_pattern(r"\)#")
                self.pool.set_session_context(self.session_id, "config")
        except Exception as e:
            logger.error(f"Error saliendo de interfaz en sesión {self.session_id}: {e}")
            raise
    
    def ensure_config_mode(self):
        """Asegura que estemos en modo config global"""
        try:
            conn = self.connect()
            
            # Si estamos en una interfaz, salir
            if self.current_context.startswith("interface"):
                logger.info(f"Asegurando modo config global en sesión {self.session_id}")
                conn.write_channel("quit\n")
                conn.read_until_pattern(r"\)#")
                self.pool.set_session_context(self.session_id, "config")
                
        except Exception as e:
            logger.error(f"Error asegurando modo config en sesión {self.session_id}: {e}")
            raise
    
    def get_current_context(self) -> str:
        """Retorna el contexto actual de la conexión"""
        return self.current_context
    
    def disconnect(self):
        """Cierra la conexión de esta sesión"""
        self.pool.disconnect_session(self.session_id)