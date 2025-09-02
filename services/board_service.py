import logging
import re
from typing import Dict

logger = logging.getLogger(__name__)

class BoardService:
    """Servicio para operaciones con tarjetas GPON"""
    
    def __init__(self, connection_service):
        self.connection_service = connection_service
    
    def obtener_puertos_tarjeta(self, tarjeta: str) -> Dict:
        """
        Obtiene informaciÃ³n de todos los puertos de una tarjeta
        Args:
            tarjeta: formato "0/2" o "0/3"
        Returns:
            Dict con informaciÃ³n de puertos y estadÃ­sticas
        """
        try:
            logger.info(f"Iniciando consulta para tarjeta {tarjeta}")
            
            # Ejecutar comando display board
            command = f"display board 0/{tarjeta} | include port"
            logger.info(f"Ejecutando comando: {command}")
            
            output = self.connection_service.execute_command(command, delay_factor=2, timeout=30)
            
            logger.info(f"Comando ejecutado, procesando output...")
            logger.debug(f"Output del comando board: {output}")
            
            # Parsear datos
            puertos_data = self._parse_board_output(output, tarjeta)
            
            logger.info(f"Se procesaron {len(puertos_data['puertos'])} puertos para tarjeta {tarjeta}")
            return puertos_data
            
        except Exception as e:
            logger.error(f"Error obteniendo puertos de tarjeta {tarjeta}: {str(e)}")
            raise Exception(f"Error en consulta de tarjeta: {str(e)}")
    
    def _parse_board_output(self, output: str, tarjeta: str) -> Dict:
        """Parsea la salida del comando display board"""
        puertos = []
        lines = output.split('\n')
        
        logger.info(f"Parseando {len(lines)} lÃ­neas de output")
        
        # PatrÃ³n para capturar: In port 0/ 2/0 , the total of ONTs are:  33, online:  31
        pattern = r'In port (\d+/\s*\d+/\d+)\s*,\s*the total of ONTs are:\s*(\d+),\s*online:\s*(\d+)'
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
                
            match = re.search(pattern, line)
            if match:
                try:
                    port_path = match.group(1).replace(' ', '')  # Remover espacios: "0/2/0"
                    total_onts = int(match.group(2))
                    online_onts = int(match.group(3))
                    
                    # Extraer solo el nÃºmero del puerto (Ãºltimo dÃ­gito)
                    puerto_numero = port_path.split('/')[-1]
                    
                    # Calcular porcentaje
                    percentage = round((online_onts / total_onts) * 100) if total_onts > 0 else 0
                    
                    # Determinar estado
                    if percentage >= 70:
                        status = 'online'
                    elif percentage >= 30:
                        status = 'warning'
                    else:
                        status = 'critical'
                    
                    puerto_info = {
                        'puerto': puerto_numero,
                        'puerto_completo': port_path,
                        'total_onts': total_onts,
                        'online_onts': online_onts,
                        'offline_onts': total_onts - online_onts,
                        'percentage': percentage,
                        'status': status
                    }
                    
                    puertos.append(puerto_info)
                    logger.debug(f"Puerto parseado: {puerto_info}")
                    
                except Exception as e:
                    logger.warning(f"Error parseando lÃ­nea {i}: {line} - {e}")
                    continue
        
        logger.info(f"Total de puertos parseados: {len(puertos)}")
        
        # Ordenar por nÃºmero de puerto
        puertos.sort(key=lambda x: int(x['puerto']))
        
        # Calcular estadÃ­sticas generales
        total_puertos = len(puertos)
        puertos_online = len([p for p in puertos if p['status'] == 'online'])
        puertos_warning = len([p for p in puertos if p['status'] == 'warning'])
        puertos_critical = len([p for p in puertos if p['status'] == 'critical'])
        
        total_onts_general = sum(p['total_onts'] for p in puertos)
        total_online_general = sum(p['online_onts'] for p in puertos)
        
        estadisticas = {
            'total_puertos': total_puertos,
            'puertos_online': puertos_online,
            'puertos_warning': puertos_warning,
            'puertos_critical': puertos_critical,
            'total_onts': total_onts_general,
            'total_online': total_online_general,
            'total_offline': total_onts_general - total_online_general
        }
        
        logger.info(f"EstadÃ­sticas calculadas: {estadisticas}")
        
        return {
            'tarjeta': tarjeta,
            'puertos': puertos,
            'estadisticas': estadisticas
        }