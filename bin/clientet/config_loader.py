#!/usr/bin/env python3
"""
Cargador de configuración para instrumentos y pines GPIO.

La configuración define:
- instruments: Mapeo de nota MIDI → pin(es) GPIO
- pines: Configuración de cada pin (nombre, tiempo activo, delay)
"""
import json
import os
import logging
from typing import Dict, List, Union
from dataclasses import dataclass

logger = logging.getLogger("clientet.config")


@dataclass
class PinConfig:
    """Configuración de un pin GPIO."""
    pin: int
    nombre: str
    tiempo: float  # Duración en segundos que el pin debe estar HIGH
    idelay: int    # Delay inicial (no usado actualmente)
    delay: int     # Delay en ms para ajustar el tiempo de ejecución


class ConfigLoader:
    """Carga y gestiona la configuración de instrumentos y pines."""
    
    def __init__(self, config_path: str = None):
        """
        Args:
            config_path: Ruta al archivo config.json. Si es None, busca en la carpeta del script.
        """
        if config_path is None:
            # Buscar config.json en la misma carpeta que este archivo
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(script_dir, "config.json")
        
        self.config_path = config_path
        self.nombre: str = ""
        self.instruments: Dict[int, List[int]] = {}  # nota → [pines]
        self.pines: Dict[int, PinConfig] = {}        # pin → config
        
        self._load_config()
    
    def _load_config(self):
        """Carga y valida el archivo de configuración."""
        try:
            logger.info(f"Cargando configuración desde: {self.config_path}")
            
            with open(self.config_path, 'r') as f:
                config_data = json.load(f)
            
            # Cargar nombre
            self.nombre = config_data.get("nombre", "Cliente")
            logger.info(f"Nombre del cliente: {self.nombre}")
            
            # Procesar instruments (nota → pines)
            raw_instruments = config_data.get("instruments", {})
            for note_str, pins in raw_instruments.items():
                note = int(note_str)
                
                # Normalizar a lista (puede ser int o lista)
                if isinstance(pins, int):
                    pins = [pins]
                elif not isinstance(pins, list):
                    logger.warning(f"Formato inválido para nota {note}: {pins}")
                    continue
                
                self.instruments[note] = pins
                logger.debug(f"Nota {note} → Pines {pins}")
            
            logger.info(f"Cargados {len(self.instruments)} mapeos de notas a pines")
            
            # Procesar pines (configuración de cada pin)
            raw_pines = config_data.get("pines", {})
            for pin_str, pin_data in raw_pines.items():
                pin = int(pin_str)
                
                pin_config = PinConfig(
                    pin=pin,
                    nombre=pin_data.get("nombre", f"Pin {pin}"),
                    tiempo=float(pin_data.get("tiempo", 0.05)),
                    idelay=int(pin_data.get("idelay", 0)),
                    delay=int(pin_data.get("delay", 0))
                )
                
                self.pines[pin] = pin_config
                logger.debug(
                    f"Pin {pin} ({pin_config.nombre}): "
                    f"tiempo={pin_config.tiempo}s, delay={pin_config.delay}ms"
                )
            
            logger.info(f"Cargados {len(self.pines)} pines GPIO")
            
        except FileNotFoundError:
            logger.error(f"❌ Archivo de configuración no encontrado: {self.config_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"❌ Error parseando JSON: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Error cargando configuración: {e}")
            raise
    
    def get_pins_for_note(self, note: int) -> List[int]:
        """
        Obtiene la lista de pines GPIO asociados a una nota MIDI.
        
        Args:
            note: Número de nota MIDI (0-127)
            
        Returns:
            Lista de pines GPIO (puede estar vacía si la nota no está mapeada)
        """
        return self.instruments.get(note, [])
    
    def get_pin_config(self, pin: int) -> PinConfig:
        """
        Obtiene la configuración de un pin GPIO.
        
        Args:
            pin: Número de pin GPIO
            
        Returns:
            PinConfig del pin
            
        Raises:
            KeyError: Si el pin no está configurado
        """
        if pin not in self.pines:
            raise KeyError(f"Pin {pin} no está configurado en config.json")
        return self.pines[pin]
    
    def get_all_pins(self) -> List[int]:
        """Retorna lista de todos los pines configurados."""
        return list(self.pines.keys())
    
    def calculate_execution_delay(self, pin: int, base_delay_ms: int = 1000) -> int:
        """
        Calcula el delay de ejecución ajustado para un pin.
        
        Formula: delay_ejecución = base_delay - pin.delay
        
        Args:
            pin: Número de pin GPIO
            base_delay_ms: Delay base en milisegundos (default: 1000ms = 1 segundo)
            
        Returns:
            Delay ajustado en milisegundos
        """
        pin_config = self.get_pin_config(pin)
        adjusted_delay = base_delay_ms - pin_config.delay
        return max(0, adjusted_delay)  # No permitir delays negativos


if __name__ == '__main__':
    # Test del cargador de configuración
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s.%(msecs)03d %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    config = ConfigLoader()
    
    print("\n" + "="*60)
    print(f"Cliente: {config.nombre}")
    print("="*60)
    
    print("\n📋 Mapeo de notas a pines:")
    for note in sorted(config.instruments.keys()):
        pins = config.get_pins_for_note(note)
        pin_names = [config.get_pin_config(p).nombre for p in pins]
        print(f"  Nota {note:3d} → Pines {pins} ({', '.join(pin_names)})")
    
    print("\n🔌 Configuración de pines:")
    for pin in sorted(config.get_all_pins()):
        pin_cfg = config.get_pin_config(pin)
        exec_delay = config.calculate_execution_delay(pin)
        print(f"  Pin {pin:2d} - {pin_cfg.nombre:10s} | "
              f"Activo: {pin_cfg.tiempo:.3f}s | "
              f"Delay: {pin_cfg.delay:3d}ms → Ejecutar en {exec_delay}ms")
