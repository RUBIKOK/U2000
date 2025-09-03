from typing import List, Dict
import logging
from models.ont_model import ONT, ONTCollection
from services.connection_service import ConnectionService

logger = logging.getLogger(__name__)

class ONTService:
    """Servicio para operaciones con ONTs"""
    
    def __init__(self, connection_service: ConnectionService):
        self.connection_service = connection_service
    
    def obtener_onts(self, tarjeta: str, puerto: str) -> ONTCollection:
        """Obtiene información de ONTs para un puerto específico"""
        try:
            logger.info(f"Iniciando consulta de ONTs para tarjeta {tarjeta}, puerto {puerto}")
            
            # Entrar a la interfaz GPON
            self.connection_service.enter_interface(tarjeta)
            
            # Ejecutar comandos en la interfaz
            output_optical = self.connection_service.execute_command(
                f"display ont optical-info {puerto} all"
            )
            
            output_summary = self.connection_service.execute_command(
                f"display ont info summary {puerto}"
            )
            
            # IMPORTANTE: Salir de la interfaz después de la consulta
            self.connection_service.exit_interface()
            
            # Debug
            logger.debug(f"Output Summary: {output_summary}")
            logger.debug(f"Output Optical: {output_optical}")
            
            # Parsear datos
            onts_data = self._parse_ont_data(output_summary, output_optical, tarjeta, puerto)
            
            # Crear colección
            collection = ONTCollection()
            for ont_data in onts_data.values():
                ont = ONT(**ont_data)
                collection.add_ont(ont)
            
            logger.info(f"Se procesaron {collection.get_total_count()} ONTs. Contexto actual: {self.connection_service.get_current_context()}")
            return collection
            
        except Exception as e:
            logger.error(f"Error obteniendo ONTs para {tarjeta}/{puerto}: {e}")
            # Asegurar que salimos de la interfaz en caso de error
            try:
                self.connection_service.exit_interface()
            except:
                pass
            raise
    
    def obtener_autofind_onts(self) -> List[Dict[str, str]]:
        """Obtiene información de ONTs detectadas automáticamente (autofind)"""
        try:
            logger.info("Iniciando consulta de autofind ONTs")
            
            # Asegurar que estamos en modo config global antes del comando autofind
            self.connection_service.ensure_config_mode()
            
            # Ejecutar comando autofind usando el método para comandos globales
            output_autofind = self.connection_service.execute_global_command("display ont autofind all")
            
            logger.debug(f"Output Autofind: {output_autofind}")
            
            # Parsear datos
            autofind_onts = self._parse_autofind_data(output_autofind)
            
            logger.info(f"Se encontraron {len(autofind_onts)} ONTs en autofind. Contexto actual: {self.connection_service.get_current_context()}")
            return autofind_onts
            
        except Exception as e:
            logger.error(f"Error obteniendo ONTs autofind: {e}")
            # Asegurar modo config en caso de error
            try:
                self.connection_service.ensure_config_mode()
            except:
                pass
            raise
    
    def _parse_autofind_data(self, output_autofind: str) -> List[Dict[str, str]]:
        """Parsea la información del comando display ont autofind all (formato de bloques)"""
        autofind_onts = []
        
        # Dividir por bloques usando la línea de separación
        blocks = output_autofind.split('----------------------------------------------------------------------------')
        
        for block in blocks:
            if not block.strip():
                continue
                
            # Parsear cada bloque
            ont_data = self._parse_autofind_block(block.strip())
            if ont_data:
                autofind_onts.append(ont_data)
        
        return autofind_onts
    
    def _parse_autofind_block(self, block: str) -> Dict[str, str]:
        """Parsea un bloque individual de autofind"""
        ont_data = {}
        
        lines = block.split('\n')
        
        for line in lines:
            line = line.strip()
            if ':' not in line:
                continue
                
            # Dividir por el primer ':'
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()
            
            # Mapear los campos que necesitamos
            if key == 'Number':
                ont_data['number'] = value
            elif key == 'F/S/P':
                ont_data['fsp'] = value
                # Parsear F/S/P para obtener board y port
                fsp_parts = value.split('/')
                if len(fsp_parts) == 3:
                    frame = fsp_parts[0]
                    slot = fsp_parts[1]  # board/tarjeta
                    port = fsp_parts[2]
                    ont_data['board'] = slot
                    ont_data['port'] = port
            elif key == 'ONT NNI type':
                ont_data['nni_type'] = value
                # Determinar tipo de PON basado en NNI type
                if '2.5G/1.25G' in value:
                    ont_data['pon_type'] = 'GPON'
                elif '10G' in value:
                    ont_data['pon_type'] = 'XG-PON'
                else:
                    ont_data['pon_type'] = 'EPON'
            elif key == 'Ont SN':
                # Formato: 4750544600D35288 (GPTF-00D35288)
                ont_data['sn_hex'] = value.split('(')[0].strip() if '(' in value else value
                if '(' in value and ')' in value:
                    ont_data['sn'] = value.split('(')[1].split(')')[0].strip()
                else:
                    ont_data['sn'] = value
            elif key == 'VendorID':
                ont_data['vendor_id'] = value
            elif key == 'Ont Version':
                ont_data['ont_version'] = value
            elif key == 'Ont SoftwareVersion':
                ont_data['software_version'] = value
            elif key == 'Ont EquipmentID':
                ont_data['equipment_id'] = value
                ont_data['type'] = value  # Usar equipment_id como type
            elif key == 'Ont autofind time':
                ont_data['autofind_time'] = value
            elif key == 'Password':
                ont_data['password'] = value
            elif key == 'Loid':
                ont_data['loid'] = value
        
        # Validar que tenemos los campos mínimos necesarios
        if 'number' in ont_data and 'fsp' in ont_data and 'sn' in ont_data:
            # Valores por defecto si no se encontraron
            ont_data.setdefault('pon_type', 'GPON')
            ont_data.setdefault('type', ont_data.get('equipment_id', 'Unknown'))
            ont_data.setdefault('vendor_id', 'Unknown')
            ont_data.setdefault('board', '0')
            ont_data.setdefault('port', '0')
            
            return ont_data
        
        return None
    
    def _parse_ont_data(self, output_summary: str, output_optical: str, 
                       tarjeta: str, puerto: str) -> Dict[str, dict]:
        """Parsea los datos de salida de los comandos"""
        onts = {}
        
        # Parsear summary
        self._parse_summary_data(output_summary, onts, tarjeta, puerto)
        
        # Parsear optical info
        self._parse_optical_data(output_optical, onts)
        
        return onts
    
    def _parse_summary_data(self, output_summary: str, onts: Dict[str, dict], 
                           tarjeta: str, puerto: str):
        """Parsea la información del comando summary"""
        lines = output_summary.split('\n')
        
        estado_start = False
        desc_start = False
        
        for line in lines:
            line = line.strip()
            
            # Detectar inicio de tabla de estados
            if "ONT  Run     Last" in line:
                estado_start = True
                continue
            elif "ONT        SN        Type" in line:
                desc_start = True
                estado_start = False
                continue
            
            # Parsear estados
            if estado_start and line and not line.startswith('-'):
                parts = line.split()
                if len(parts) >= 2 and parts[0].isdigit():
                    ont_id = parts[0]
                    estado = parts[1]
                    
                    # Buscar la causa (último elemento si no es '-')
                    causa = ""
                    if len(parts) > 4 and parts[-1] != '-':
                        causa = parts[-1]
                    
                    onts[ont_id] = {
                        'id': ont_id,
                        'tarjeta': tarjeta,
                        'puerto': puerto,
                        'estado': estado,
                        'last_down_cause': causa,
                        'descripcion': ""
                    }
            
            # Parsear descripciones (segunda tabla)
            elif desc_start and line and not line.startswith('-'):
                parts = line.split()
                if len(parts) >= 6 and parts[0].isdigit():
                    ont_id = parts[0]
                    if ont_id in onts:
                        # Buscar donde termina la parte numérica y empieza la descripción
                        desc_parts = []
                        found_desc_start = False
                        
                        for part in parts:
                            if not found_desc_start:
                                # Buscar el patrón de potencia (ej: -21.36/1.40)
                                if '/' in part and '-' in part:
                                    found_desc_start = True
                                    continue
                            else:
                                desc_parts.append(part)
                        
                        if desc_parts:
                            onts[ont_id]['descripcion'] = '_'.join(desc_parts)
    
    def _parse_optical_data(self, output_optical: str, onts: Dict[str, dict]):
        """Parsea la información del comando optical"""
        optical_lines = output_optical.split('\n')
        
        for line in optical_lines:
            line = line.strip()
            if not line or line.startswith('-') or 'ONT' in line:
                continue
            
            parts = line.split()
            if len(parts) >= 6 and parts[0].isdigit():
                try:
                    ont_id = parts[0]
                    ont_rx = float(parts[1])
                    olt_rx = float(parts[3])
                    temperature = int(parts[4])
                    distance = int(parts[6])
                    
                    if ont_id in onts:
                        onts[ont_id].update({
                            'ont_rx': ont_rx,
                            'olt_rx': olt_rx,
                            'temperature': temperature,
                            'distance': distance
                        })
                except (ValueError, IndexError) as e:
                    logger.warning(f"Error parsing optical line: {line} - {e}")
                    continue