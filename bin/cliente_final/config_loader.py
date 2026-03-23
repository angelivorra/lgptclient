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
from typing import Dict, List
from dataclasses import dataclass

logger = logging.getLogger("cliente.config")


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
            config_path: Ruta al archivo config.json
        """
        if config_path is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(script_dir, "config.json")
        
        self.config_path = config_path
        self.nombre: str = ""
        self.invertir: bool = False  # Invertir pantalla de estado
        self.instruments: Dict[int, List[int]] = {}
        self.pines: Dict[int, PinConfig] = {}
        
        self._load_config()
    
    def _load_config(self):
        """Carga y valida el archivo de configuración."""
        try:
            logger.info(f"Cargando configuración desde: {self.config_path}")
            
            with open(self.config_path, 'r') as f:
                config_data = json.load(f)
            
            self.nombre = config_data.get("nombre", "Cliente")
            self.invertir = config_data.get("invertir", False)
            logger.info(f"Nombre del cliente: {self.nombre}")
            logger.info(f"Invertir pantalla: {self.invertir}")
            
            # Procesar instruments (nota → pines)
            raw_instruments = config_data.get("instruments", {})
            for note_str, pins in raw_instruments.items():
                note = int(note_str)
                
                if isinstance(pins, int):
                    pins = [pins]
                elif not isinstance(pins, list):
                    logger.warning(f"Formato inválido para nota {note}: {pins}")
                    continue
                
                self.instruments[note] = pins
                logger.debug(f"Nota {note} → Pines {pins}")
            
            logger.info(f"Cargados {len(self.instruments)} mapeos de notas a pines")
            
            # Procesar pines
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
        """Obtiene la lista de pines GPIO asociados a una nota MIDI."""
        return self.instruments.get(note, [])
    
    def get_pin_config(self, pin: int) -> PinConfig:
        """Obtiene la configuración de un pin GPIO."""
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
        """
        pin_config = self.get_pin_config(pin)
        adjusted_delay = base_delay_ms - pin_config.delay
        return max(0, adjusted_delay)
