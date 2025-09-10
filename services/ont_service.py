# services/ont_service.py - VERSIÓN CORREGIDA

import datetime
from typing import List, Dict
import logging
import re
from models.ont_model import ONT, ONTCollection

logger = logging.getLogger(__name__)

class ONTService:
    """Servicio para operaciones con ONTs"""
    
    def __init__(self, session_connection):
        """
        Args:
            session_connection: Instancia de SessionConnection del pool
        """
        self.session_connection = session_connection
    
    def obtener_onts(self, tarjeta: str, puerto: str) -> ONTCollection:
        """Obtiene información de ONTs para un puerto específico"""
        try:
            logger.info(f"Iniciando consulta de ONTs para tarjeta {tarjeta}, puerto {puerto} en sesión {self.session_connection.session_id}")
            
            # ============ CORRECCIÓN 1: Validación de parámetros ============
            if not self._validate_parameters(tarjeta, puerto):
                raise ValueError(f"Parámetros inválidos: tarjeta={tarjeta}, puerto={puerto}")
            
            # Entrar a la interfaz GPON
            self.session_connection.enter_interface(tarjeta)
            
            # ============ CORRECCIÓN 2: Manejo de timeouts mejorado ============
            try:
                # Comandos con timeouts específicos
                output_optical = self.session_connection.execute_command(
                    f"display ont optical-info {puerto} all",
                    delay_factor=2,
                    timeout=30  # Timeout más largo para optical
                )
                
                output_summary = self.session_connection.execute_command(
                    f"display ont info summary {puerto}",
                    delay_factor=2,
                    timeout=25
                )
                
            except Exception as cmd_error:
                logger.error(f"Error ejecutando comandos: {cmd_error}")
                raise Exception(f"Error en comandos de consulta: {str(cmd_error)}")
            
            finally:
                # IMPORTANTE: SIEMPRE salir de la interfaz
                try:
                    self.session_connection.exit_interface()
                except Exception as exit_error:
                    logger.warning(f"Error saliendo de interfaz: {exit_error}")
            
            # Debug con límite de caracteres
            logger.debug(f"Output Summary (primeros 500 chars): {output_summary[:500]}...")
            logger.debug(f"Output Optical (primeros 500 chars): {output_optical[:500]}...")
            
            # Parsear datos
            onts_data = self._parse_ont_data(output_summary, output_optical, tarjeta, puerto)
            
            # Crear colección
            collection = ONTCollection()
            valid_onts = 0
            
            for ont_id, ont_data in onts_data.items():
                try:
                    ont = ONT(**ont_data)
                    collection.add_ont(ont)
                    valid_onts += 1
                except Exception as ont_error:
                    logger.warning(f"Error creando ONT {ont_id}: {ont_error}")
                    continue
            
            logger.info(f"Se procesaron {valid_onts}/{len(onts_data)} ONTs válidas en sesión {self.session_connection.session_id}")
            return collection
            
        except Exception as e:
            logger.error(f"Error obteniendo ONTs para {tarjeta}/{puerto} en sesión {self.session_connection.session_id}: {e}")
            # Asegurar que salimos de la interfaz en caso de error
            try:
                self.session_connection.exit_interface()
            except:
                pass
            raise
    
    def obtener_autofind_onts(self) -> List[Dict[str, str]]:
        """Obtiene información de ONTs detectadas automáticamente (autofind)"""
        try:
            logger.info(f"Iniciando consulta de autofind ONTs en sesión {self.session_connection.session_id}")
            
            # Asegurar que estamos en modo config global antes del comando autofind
            self.session_connection.ensure_config_mode()
            
            # ============ CORRECCIÓN 3: Timeout específico para autofind ============
            # Ejecutar comando autofind con timeout largo
            output_autofind = self.session_connection.execute_global_command(
                "display ont autofind all",
                delay_factor=3,  # Factor de delay más alto
                timeout=45       # Timeout más largo para autofind
            )
            
            # Logging limitado para evitar logs enormes
            logger.debug(f"Output Autofind (primeros 1000 chars): {output_autofind[:1000]}...")
            
            # Parsear datos
            autofind_onts = self._parse_autofind_data(output_autofind)
            
            logger.info(f"Se encontraron {len(autofind_onts)} ONTs en autofind en sesión {self.session_connection.session_id}")
            return autofind_onts
            
        except Exception as e:
            logger.error(f"Error obteniendo ONTs autofind en sesión {self.session_connection.session_id}: {e}")
            # Asegurar modo config en caso de error
            try:
                self.session_connection.ensure_config_mode()
            except:
                pass
            raise
    
    # ============ CORRECCIÓN 4: Validación de parámetros ============
    def _validate_parameters(self, tarjeta: str, puerto: str) -> bool:
        """Valida los parámetros de entrada"""
        try:
            # Validar tarjeta (1-17)
            if not re.match(r'^(1[0-7]|[1-9])$', tarjeta):
                logger.error(f"Tarjeta inválida: {tarjeta}")
                return False
            
            # Validar puerto (0-15)
            if not re.match(r'^(1[0-5]|[0-9])$', puerto):
                logger.error(f"Puerto inválido: {puerto}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"Error validando parámetros: {e}")
            return False
    
    def _parse_autofind_data(self, output_autofind: str) -> List[Dict[str, str]]:
        """Parsea la información del comando display ont autofind all (formato de bloques)"""
        autofind_onts = []
        
        # ============ CORRECCIÓN 5: Parsing más robusto ============
        if not output_autofind or len(output_autofind.strip()) < 10:
            logger.warning("Output de autofind vacío o muy corto")
            return autofind_onts
        
        # Dividir por bloques usando la línea de separación
        separator_patterns = [
            '----------------------------------------------------------------------------',
            '---------------------------------------------------------------------',
            '═' * 50  # Por si usa otro tipo de separador
        ]
        
        blocks = [output_autofind]  # Inicializar con el texto completo
        
        # Intentar diferentes separadores
        for separator in separator_patterns:
            if separator in output_autofind:
                blocks = output_autofind.split(separator)
                break
        
        # Si no hay separadores, intentar por bloques de texto
        if len(blocks) == 1:
            blocks = self._split_by_ont_blocks(output_autofind)
        
        processed_blocks = 0
        valid_onts = 0
        
        for block in blocks:
            processed_blocks += 1
            if not block.strip():
                continue
                
            # Parsear cada bloque
            ont_data = self._parse_autofind_block(block.strip())
            if ont_data:
                autofind_onts.append(ont_data)
                valid_onts += 1
        
        logger.info(f"Autofind parsing: {processed_blocks} bloques procesados, {valid_onts} ONTs válidas")
        return autofind_onts
    
    # ============ CORRECCIÓN 6: Método alternativo de splitting ============
    def _split_by_ont_blocks(self, text: str) -> List[str]:
        """Divide el texto en bloques basado en patrones de ONT"""
        blocks = []
        current_block = []
        
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Detectar inicio de nuevo bloque (contiene "Number:" al inicio)
            if line.startswith('Number:') and current_block:
                # Guardar bloque actual
                blocks.append('\n'.join(current_block))
                current_block = [line]
            else:
                current_block.append(line)
        
        # Agregar último bloque
        if current_block:
            blocks.append('\n'.join(current_block))
        
        return blocks
    
    def _parse_autofind_block(self, block: str) -> Dict[str, str]:
        """Parsea un bloque individual de autofind"""
        ont_data = {}
        
        lines = block.split('\n')
        
        for line in lines:
            line = line.strip()
            if ':' not in line:
                continue
                
            # Dividir por el primer ':'
            try:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
            except ValueError:
                continue
            
            # ============ CORRECCIÓN 7: Parsing más robusto de campos ============
            # Mapear los campos que necesitamos
            if key == 'Number':
                ont_data['number'] = value
            elif key == 'F/S/P':
                ont_data['fsp'] = value
                # Parsear F/S/P para obtener board y port
                fsp_parts = value.split('/')
                if len(fsp_parts) == 3:
                    try:
                        frame = fsp_parts[0]
                        slot = fsp_parts[1]  # board/tarjeta
                        port = fsp_parts[2]
                        ont_data['board'] = slot
                        ont_data['port'] = port
                    except (IndexError, ValueError) as e:
                        logger.warning(f"Error parseando F/S/P '{value}': {e}")
            elif key == 'ONT NNI type':
                ont_data['nni_type'] = value
                # Determinar tipo de PON basado en NNI type
                if '2.5G/1.25G' in value or 'GPON' in value.upper():
                    ont_data['pon_type'] = 'GPON'
                elif '10G' in value or 'XG-PON' in value.upper():
                    ont_data['pon_type'] = 'XG-PON'
                elif 'EPON' in value.upper():
                    ont_data['pon_type'] = 'EPON'
                else:
                    ont_data['pon_type'] = 'GPON'  # Default
            elif key == 'Ont SN':
                # Formato: 4750544600D35288 (GPTF-00D35288)
                ont_data['sn_hex'] = value.split('(')[0].strip() if '(' in value else value
                if '(' in value and ')' in value:
                    ont_data['sn'] = value.split('(')[1].split(')')[0].strip()
                else:
                    # Si no hay formato con paréntesis, usar el valor completo
                    ont_data['sn'] = value
                    
                # ============ CORRECCIÓN 8: Limpieza y validación de SN ============
                # Limpiar el SN
                if ont_data['sn']:
                    ont_data['sn'] = re.sub(r'[^A-Za-z0-9-]', '', ont_data['sn'])
                    
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
        
        # ============ CORRECCIÓN 9: Validación de datos mínimos ============
        # Validar que tenemos los campos mínimos necesarios
        required_fields = ['number', 'fsp', 'sn']
        missing_fields = [field for field in required_fields if not ont_data.get(field)]
        
        if missing_fields:
            logger.warning(f"Bloque autofind incompleto, faltan campos: {missing_fields}")
            return None
        
        # Validar longitud de SN
        if len(ont_data['sn']) < 8:
            logger.warning(f"SN muy corto: {ont_data['sn']}")
            return None
        
        # Valores por defecto si no se encontraron
        ont_data.setdefault('pon_type', 'GPON')
        ont_data.setdefault('type', ont_data.get('equipment_id', 'Unknown'))
        ont_data.setdefault('vendor_id', 'Unknown')
        ont_data.setdefault('board', '0')
        ont_data.setdefault('port', '0')
        
        return ont_data
    
    def _parse_ont_data(self, output_summary: str, output_optical: str, 
                       tarjeta: str, puerto: str) -> Dict[str, dict]:
        """Parsea los datos de salida de los comandos"""
        onts = {}
        
        # ============ CORRECCIÓN 10: Validación de outputs ============
        if not output_summary or len(output_summary.strip()) < 10:
            logger.warning("Output summary vacío o muy corto")
            return onts
        
        if not output_optical or len(output_optical.strip()) < 10:
            logger.warning("Output optical vacío o muy corto")
        
        # Parsear summary
        try:
            self._parse_summary_data(output_summary, onts, tarjeta, puerto)
        except Exception as e:
            logger.error(f"Error parseando summary data: {e}")
        
        # Parsear optical info
        try:
            self._parse_optical_data(output_optical, onts)
        except Exception as e:
            logger.error(f"Error parseando optical data: {e}")
        
        return onts
    
    def _parse_summary_data(self, output_summary: str, onts: Dict[str, dict], 
                           tarjeta: str, puerto: str):
        """Parsea la información del comando summary"""
        lines = output_summary.split('\n')
        
        estado_start = False
        desc_start = False
        lines_processed = 0
        onts_found = 0
        
        for line in lines:
            line = line.strip()
            lines_processed += 1
            
            # Detectar inicio de tabla de estados
            if "ONT  Run     Last" in line or "ONT-ID  Run-state" in line:
                estado_start = True
                desc_start = False
                continue
            elif "ONT        SN        Type" in line or "ONT-ID        SN" in line:
                desc_start = True
                estado_start = False
                continue
            
            # ============ CORRECCIÓN 11: Parsing más robusto de estados ============
            # Parsear estados
            if estado_start and line and not line.startswith('-') and not line.startswith('ONT'):
                parts = line.split()
                if len(parts) >= 2 and parts[0].isdigit():
                    try:
                        ont_id = parts[0]
                        estado = parts[1] if len(parts) > 1 else 'unknown'

                        # Inicializar valores
                        causa = ""
                        last_down_time = ""

                        # Parsing mejorado de fecha/hora/causa
                        if len(parts) > 3:
                            # Buscar patrón de fecha (YYYY-MM-DD o similar)
                            date_pattern = r'\d{4}-\d{2}-\d{2}'
                            time_pattern = r'\d{2}:\d{2}:\d{2}'
                            
                            date_found = None
                            time_found = None
                            
                            for i, part in enumerate(parts[2:], 2):  # Empezar después de ONT-ID y estado
                                if re.match(date_pattern, part):
                                    date_found = part
                                    if i + 1 < len(parts) and re.match(time_pattern, parts[i + 1]):
                                        time_found = parts[i + 1]
                                        if i + 2 < len(parts):
                                            causa = parts[i + 2]
                                    break
                            
                            if date_found and time_found:
                                last_down_time = f"{date_found} {time_found}"

                        onts[ont_id] = {
                            'id': ont_id,
                            'tarjeta': tarjeta,
                            'puerto': puerto,
                            'estado': estado,
                            'last_down_cause': causa if causa != "-" else "",
                            'last_down_time': last_down_time,
                            'descripcion': ""
                        }
                        onts_found += 1
                        
                    except (IndexError, ValueError) as e:
                        logger.warning(f"Error parseando línea de estado: '{line}' - {e}")
                        continue
            
            # ============ CORRECCIÓN 12: Parsing mejorado de descripciones ============
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

        logger.info(f"Summary parsing: {lines_processed} líneas procesadas, {onts_found} ONTs encontradas")

    def _parse_optical_data(self, output_optical: str, onts: Dict[str, dict]):
        """Parsea la información del comando optical"""
        optical_lines = output_optical.split('\n')
        optical_parsed = 0
        
        for line in optical_lines:
            line = line.strip()
            if not line or line.startswith('-') or 'ONT' in line:
                continue
            
            parts = line.split()
            
            # ============ CORRECCIÓN 13: Parsing más robusto de datos ópticos ============
            if len(parts) >= 6 and parts[0].isdigit():
                try:
                    ont_id = parts[0]
                    
                    # Parsing más cuidadoso de valores numéricos
                    ont_rx = self._safe_float_parse(parts[1])
                    olt_rx = self._safe_float_parse(parts[3])
                    temperature = self._safe_int_parse(parts[4])
                    distance = self._safe_int_parse(parts[6])
                    
                    if ont_id in onts:
                        onts[ont_id].update({
                            'ont_rx': ont_rx,
                            'olt_rx': olt_rx,
                            'temperature': temperature,
                            'distance': distance
                        })
                        optical_parsed += 1
                    else:
                        logger.warning(f"ONT {ont_id} encontrada en optical pero no en summary")
                        
                except (ValueError, IndexError) as e:
                    logger.warning(f"Error parsing optical line: '{line}' - {e}")
                    continue
        
        logger.info(f"Optical parsing: {optical_parsed} ONTs con datos ópticos")

    # ============ CORRECCIÓN 14: Funciones auxiliares para parsing seguro ============
    def _safe_float_parse(self, value: str) -> float:
        """Parsea un valor float de manera segura"""
        try:
            # Limpiar el valor
            cleaned = re.sub(r'[^\d\-.]', '', str(value))
            if cleaned and cleaned != '-':
                return float(cleaned)
        except (ValueError, TypeError):
            pass
        return None

    def _safe_int_parse(self, value: str) -> int:
        """Parsea un valor int de manera segura"""
        try:
            # Limpiar el valor
            cleaned = re.sub(r'[^\d]', '', str(value))
            if cleaned:
                return int(cleaned)
        except (ValueError, TypeError):
            pass
        return None
    
    def obtener_detalles_ont(self, tarjeta: str, puerto: str, ont_id: str) -> str:
        """Obtiene información detallada de una ONT específica y limpia el output"""
        try:
            logger.info(f"Obteniendo detalles para ONT {ont_id} en {tarjeta}/{puerto} en sesión {self.session_connection.session_id}")
            
            # Entrar a la interfaz
            self.session_connection.enter_interface(tarjeta)
            
            try:
                # Comandos con timeouts específicos
                outputinfo = self.session_connection.execute_command(
                    f"display ont info {puerto} {ont_id}",
                    delay_factor=2,
                    timeout=30  # Timeout más largo para optical
                )
                
                outputhistory = self.session_connection.execute_command(
                    f"display ont register-info {puerto} {ont_id}",
                    delay_factor=2,
                    timeout=25
                )
                
            except Exception as cmd_error:
                logger.error(f"Error ejecutando comandos: {cmd_error}")
                raise Exception(f"Error en comandos de consulta: {str(cmd_error)}")
            
            finally:
                # IMPORTANTE: SIEMPRE salir de la interfaz
                try:
                    self.session_connection.exit_interface()
                except Exception as exit_error:
                    logger.warning(f"Error saliendo de interfaz: {exit_error}")
            
            # # Limpiar el output - remover líneas del prompt y input
            cleaned_output_info = self.obtener_info_basica_ont(outputinfo)
            cleaned_output_history = self._formatear_tabla_registros(outputhistory)

            # Unir ambas salidas
            resultado = "="*50 + "\n"
            resultado += "INFORMACIÓN BÁSICA DE LA ONT\n"
            resultado += "="*50 + "\n"
            resultado += cleaned_output_info + "\n\n"
            
            resultado += "="*50 + "\n"
            resultado += "HISTORIAL\n"
            resultado += "="*50 + "\n"
            resultado += cleaned_output_history
        
            logger.info(f"Detalles completos de ONT {ont_id} obtenidos exitosamente")
            return resultado
            
        except Exception as e:
            logger.error(f"Error obteniendo detalles de ONT {ont_id}: {e}")
            # Asegurar que salimos de la interfaz en caso de error
            try:
                self.session_connection.exit_interface()
            except:
                pass
            raise

    def obtener_info_basica_ont(self, output: str) -> str:
        """Extrae solo la sección de información básica hasta Global ONT-ID"""
        lines = output.split('\n')
        basic_info_lines = []
        start_found = False
        
        for line in lines:
            line = line.strip()
            
            if not line:
                continue
                
            # Buscar el inicio de la información básica
            if 'F/S/P' in line and ':' in line:
                start_found = True
                
            if start_found:
                basic_info_lines.append(line)
                
                # Detener cuando llegamos al final de la sección básica
                if 'Global ONT-ID' in line and ':' in line:
                    break
                    
                # También detener si encontramos el próximo separador con contenido después del inicio
                if '------------' in line and len(basic_info_lines) > 5:
                    # Remover la última línea (el separador)
                    if basic_info_lines and '------------' in basic_info_lines[-1]:
                        basic_info_lines.pop()
                    break
        
        return '\n'.join(basic_info_lines)      
    
    def _formatear_tabla_registros(self, output_text: str) -> str:
        """Formatea el output de display ont register-info como tabla"""
        try:
            # Asegurarnos de que trabajamos con texto
            if not isinstance(output_text, str):
                output_text = str(output_text)
                
            lines = output_text.split('\n')
            registros = []
            registro_actual = {}
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                # Parsear líneas con formato "Clave : Valor"
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    if key == 'Index':
                        if registro_actual:  # Guardar registro anterior
                            registros.append(registro_actual)
                        registro_actual = {'index': value}
                    elif key == 'Auth-type':
                        registro_actual['auth_type'] = value
                    elif key == 'SN':
                        registro_actual['sn'] = value
                    elif key == 'TYPE':
                        registro_actual['type'] = value
                    elif key == 'UpTime':
                        registro_actual['up_time'] = value
                    elif key == 'DownTime':
                        registro_actual['down_time'] = value
                    elif key == 'DownCause':
                        registro_actual['down_cause'] = value
            
            # Agregar el último registro
            if registro_actual:
                registros.append(registro_actual)
            
            # Crear tabla formateada
            tabla = "HISTÓRICO DE REGISTROS:\n"
            tabla += "#   UP AUTH TIME             OFFLINE TIME              DOWN REASON\n"
            tabla += "-" * 80 + "\n"
            
            for registro in registros:
                index = registro.get('index', '')
                up_time = registro.get('up_time', '')
                down_time = registro.get('down_time', '-')
                down_cause = registro.get('down_cause', '-')
                
                if down_time == '-':
                    linea = f"{index:2}  {up_time:23}   ONU is currently online"
                else:
                    linea = f"{index:2}  {up_time:23}   {down_time:23}   {down_cause}"
                
                tabla += linea + "\n"
            
            return tabla
            
        except Exception as e:
            logger.error(f"Error formateando tabla de registros: {e}")
            return f"Error al formatear histórico: {str(e)}\nOutput original:\n{output_text}"