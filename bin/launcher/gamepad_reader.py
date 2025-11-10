#!/usr/bin/env python3
"""
Módulo para leer eventos de gamepad/joystick USB y convertirlos a eventos de teclado.
Usa evdev para leer eventos del dispositivo.
Carga configuración personalizada desde gamepad_config.json si existe.
"""

import json
import os
import threading
import time
from typing import Optional, Callable, Dict, Any
import logging


def load_gamepad_config(config_path: str = None) -> Optional[Dict[str, Any]]:
    """
    Carga la configuración del gamepad desde un archivo JSON.
    
    Args:
        config_path: Ruta al archivo de configuración. Si es None, busca en la ubicación por defecto.
    
    Returns:
        Diccionario con la configuración o None si no existe
    """
    if config_path is None:
        # Buscar en el mismo directorio que este script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(script_dir, 'gamepad_config.json')
    
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
                logging.info(f"Configuración de gamepad cargada desde: {config_path}")
                return config
    except Exception as e:
        logging.warning(f"No se pudo cargar configuración de gamepad: {e}")
    
    return None


class GamepadReader:
    """Lee eventos de un gamepad USB y los convierte a comandos"""
    
    def __init__(self, device_path: str = "/dev/input/event0", callback: Optional[Callable] = None, config_path: str = None):
        """
        Inicializa el lector de gamepad
        
        Args:
            device_path: Ruta al dispositivo de evento (ej: /dev/input/event0)
            callback: Función a llamar cuando se detecta un evento
                      Firma: callback(event_type: str) donde event_type puede ser:
                      'up', 'down', 'select', etc.
            config_path: Ruta al archivo de configuración JSON (opcional)
        """
        self.device_path = device_path
        self.callback = callback
        self.running = False
        self.thread = None
        self.device = None
        
        # Cargar configuración personalizada
        self.custom_config = load_gamepad_config(config_path)
        
        # Estado de ejes para evitar repeticiones
        self.axis_states = {}  # {code: value}
    
    def start(self) -> bool:
        """
        Inicia la lectura de eventos del gamepad en un thread separado
        
        Returns:
            True si se inició correctamente, False si hubo error
        """
        try:
            import evdev
            
            # Intentar abrir el dispositivo
            try:
                self.device = evdev.InputDevice(self.device_path)
                logging.info(f"Gamepad detectado: {self.device.name} en {self.device_path}")
            except (FileNotFoundError, PermissionError) as e:
                logging.warning(f"No se pudo abrir gamepad en {self.device_path}: {e}")
                # Intentar buscar automáticamente
                devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
                gamepad_devices = [
                    dev for dev in devices 
                    if 'gamepad' in dev.name.lower() or 'joystick' in dev.name.lower()
                ]
                
                if gamepad_devices:
                    self.device = gamepad_devices[0]
                    logging.info(f"Gamepad encontrado automáticamente: {self.device.name}")
                else:
                    logging.warning("No se encontró ningún gamepad")
                    return False
            
            # Iniciar thread de lectura
            self.running = True
            self.thread = threading.Thread(target=self._read_loop, daemon=True)
            self.thread.start()
            return True
            
        except ImportError:
            logging.error("evdev no está instalado. Instálalo con: pip install evdev")
            return False
        except Exception as e:
            logging.error(f"Error iniciando gamepad reader: {e}")
            return False
    
    def stop(self):
        """Detiene la lectura de eventos"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        if self.device:
            self.device.close()
    
    def _read_loop(self):
        """Loop principal de lectura de eventos"""
        import evdev
        
        try:
            for event in self.device.read_loop():
                if not self.running:
                    break
                
                # Filtrar solo eventos de botones y ejes
                if event.type == evdev.ecodes.EV_KEY:
                    self._handle_button_event(event)
                elif event.type == evdev.ecodes.EV_ABS:
                    self._handle_axis_event(event)
                    
        except Exception as e:
            logging.error(f"Error en gamepad read loop: {e}")
    
    def _handle_button_event(self, event):
        """Maneja eventos de botones"""
        import evdev
        
        # Solo procesar cuando se presiona el botón (value=1), no cuando se suelta (value=0)
        if event.value != 1:
            return
        
        event_name = None
        
        # Si hay configuración personalizada, usarla primero
        if self.custom_config and 'mappings' in self.custom_config:
            for action, mapping in self.custom_config['mappings'].items():
                if mapping['type'] == 'button' and mapping['code'] == event.code:
                    event_name = action
                    break
        
        # Si no hay match en configuración personalizada, usar mapeo por defecto
        if event_name is None:
            if event.code in [304, 305, 288]:  # BTN_A, BTN_B, o TRIGGER
                event_name = 'select'  # Botón de acción
            elif event.code == 315:  # BTN_START
                event_name = 'start'
            elif event.code == 314:  # BTN_SELECT
                event_name = 'back'
            elif event.code == 307:  # BTN_X
                event_name = 'button_x'
            elif event.code == 308:  # BTN_Y
                event_name = 'button_y'
        
        if event_name and self.callback:
            self.callback(event_name)
    
    def _handle_axis_event(self, event):
        """Maneja eventos de ejes (D-pad, joysticks) usando configuración personalizada"""
        import evdev
        
        event_name = None
        
        # Obtener valor anterior del eje
        prev_value = self.axis_states.get(event.code, 128)
        self.axis_states[event.code] = event.value
        
        # Detectar si estamos en posición neutral
        is_neutral = 126 <= event.value <= 130
        was_neutral = 126 <= prev_value <= 130
        
        # Solo procesar transiciones DESDE neutral HACIA una dirección
        # Esto evita capturar el evento de "soltar" como una acción
        if not (was_neutral and not is_neutral):
            return
        
        # Si hay configuración personalizada, usarla
        if self.custom_config and 'mappings' in self.custom_config:
            for action, mapping in self.custom_config['mappings'].items():
                if mapping['type'] == 'axis' and mapping['code'] == event.code:
                    # Verificar que el valor coincida (con tolerancia)
                    target_value = mapping['value']
                    tolerance = 10
                    
                    if abs(event.value - target_value) <= tolerance:
                        event_name = action
                        break
        
        # Si no hay match en configuración personalizada, usar mapeo por defecto
        if event_name is None:
            # D-pad horizontal
            if event.code == 16:  # ABS_HAT0X
                if event.value == -1:
                    event_name = 'left'
                elif event.value == 1:
                    event_name = 'right'
            
            # D-pad vertical
            elif event.code == 17:  # ABS_HAT0Y
                if event.value == -1:
                    event_name = 'up'
                elif event.value == 1:
                    event_name = 'down'
            
            # Joystick izquierdo vertical
            elif event.code == 1:  # ABS_Y
                if event.value < 64:  # Hacia arriba
                    event_name = 'up'
                elif event.value > 192:  # Hacia abajo
                    event_name = 'down'
        
        if event_name and self.callback:
            self.callback(event_name)


# Función auxiliar para instalar evdev si no está disponible
def check_evdev_installed() -> bool:
    """Verifica si evdev está instalado"""
    try:
        import evdev
        return True
    except ImportError:
        return False


if __name__ == "__main__":
    # Prueba simple
    logging.basicConfig(level=logging.INFO)
    
    def test_callback(event_type: str):
        print(f"Evento: {event_type}")
    
    reader = GamepadReader(callback=test_callback)
    
    if reader.start():
        print("Gamepad listo. Presiona botones (Ctrl+C para salir)...")
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nDeteniendo...")
    else:
        print("No se pudo iniciar el gamepad reader")
    
    reader.stop()
