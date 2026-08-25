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
        """Carga inicial desde el fichero local, si existe. Es solo un
        FALLBACK de arranque: la fuente única es el sinte, que manda la config
        por TCP (RCONFIG) al conectar y sobreescribe esto. Si no hay fichero,
        la robota arranca sin config y espera al RCONFIG."""
        try:
            with open(self.config_path, 'r') as f:
                config_data = json.load(f)
        except FileNotFoundError:
            logger.warning(
                f"⚠️  Sin config local ({self.config_path}); "
                "esperando RCONFIG del sinte")
            return
        except json.JSONDecodeError as e:
            logger.error(f"❌ Error parseando JSON local: {e}")
            return
        logger.info(f"Cargando config local (fallback): {self.config_path}")
        self.load_from_dict(config_data)

    def load_from_dict(self, config_data: dict):
        """(Re)construye la config desde un dict (fichero local o RCONFIG del
        sinte). Reemplaza instruments/pines por completo."""
        self.nombre = config_data.get("nombre", "Cliente")
        self.invertir = config_data.get("invertir", False)
        logger.info(f"Nombre del cliente: {self.nombre}")
        logger.info(f"Invertir pantalla: {self.invertir}")

        # Procesar instruments (nota → pines)
        instruments: Dict[int, List[int]] = {}
        for note_str, pins in config_data.get("instruments", {}).items():
            note = int(note_str)
            if isinstance(pins, int):
                pins = [pins]
            elif not isinstance(pins, list):
                logger.warning(f"Formato inválido para nota {note}: {pins}")
                continue
            instruments[note] = pins
            logger.debug(f"Nota {note} → Pines {pins}")
        self.instruments = instruments
        logger.info(f"Cargados {len(self.instruments)} mapeos de notas a pines")

        # Procesar pines
        pines: Dict[int, PinConfig] = {}
        for pin_str, pin_data in config_data.get("pines", {}).items():
            pin = int(pin_str)
            pines[pin] = PinConfig(
                pin=pin,
                nombre=pin_data.get("nombre", f"Pin {pin}"),
                tiempo=float(pin_data.get("tiempo", 0.05)),
                idelay=int(pin_data.get("idelay", 0)),
                delay=int(pin_data.get("delay", 0)),
            )
        self.pines = pines
        logger.info(f"Cargados {len(self.pines)} pines GPIO")
    
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

    def set_pin_override(self, pin: int, tiempo_s: float, delay_ms: int):
        """Sobreescribe en memoria tiempo/delay de un pin (calibración en vivo)."""
        pin_config = self.get_pin_config(pin)
        pin_config.tiempo = tiempo_s
        pin_config.delay = delay_ms
        logger.info(
            f"🎛️  Calibración en memoria - Pin {pin} ({pin_config.nombre}): "
            f"tiempo={tiempo_s}s, delay={delay_ms}ms"
        )

    def calculate_execution_delay(self, pin: int, base_delay_ms: int = 1000) -> int:
        """
        Calcula el delay de ejecución ajustado para un pin.
        Formula: delay_ejecución = base_delay - pin.delay
        """
        pin_config = self.get_pin_config(pin)
        adjusted_delay = base_delay_ms - pin_config.delay
        return max(0, adjusted_delay)
