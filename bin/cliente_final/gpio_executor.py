#!/usr/bin/env python3
"""
Ejecutor de acciones GPIO con timing preciso.

Gestiona la activación de pines GPIO:
- Inicializa los pines según configuración
- Activa pines (HIGH) por un tiempo específico
- Desactiva automáticamente (LOW)
"""
import asyncio
import logging
import time
from typing import Set

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    logging.warning("RPi.GPIO no disponible - modo simulación")

logger = logging.getLogger("cliente.gpio")


class GPIOExecutor:
    """Ejecutor de acciones GPIO con soporte para activaciones temporales."""
    
    def __init__(self, simulate: bool = None):
        """
        Args:
            simulate: Si True, simula GPIO sin hardware real.
        """
        if simulate is None:
            simulate = not GPIO_AVAILABLE
        
        self.simulate = simulate
        self.initialized = False
        self.configured_pins: Set[int] = set()
        self._active_pins: Set[int] = set()
        self._pin_locks = {}
    
    def initialize(self, pins: list[int]):
        """Inicializa los pines GPIO."""
        if self.initialized:
            logger.warning("GPIO ya inicializado")
            return
        
        if self.simulate:
            logger.info("🔧 Modo simulación - GPIO no se inicializará realmente")
            self.configured_pins = set(pins)
            self.initialized = True
            for pin in pins:
                logger.debug(f"   [SIM] Pin {pin} configurado como OUTPUT")
            return
        
        try:
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            
            for pin in pins:
                GPIO.setup(pin, GPIO.OUT)
                GPIO.output(pin, GPIO.LOW)
                self.configured_pins.add(pin)
                self._pin_locks[pin] = asyncio.Lock()
                logger.debug(f"✅ Pin {pin} configurado como OUTPUT (LOW)")
            
            self.initialized = True
            logger.info(f"✅ GPIO inicializado correctamente ({len(pins)} pines)")
            
        except Exception as e:
            logger.error(f"❌ Error inicializando GPIO: {e}")
            raise
    
    def cleanup(self):
        """Limpia los pines GPIO."""
        if not self.initialized:
            return
        
        if self.simulate:
            logger.debug("🔧 [SIM] GPIO cleanup")
            self.initialized = False
            self.configured_pins.clear()
            return
        
        try:
            logger.debug("Limpiando GPIO...")
            GPIO.cleanup()
            self.initialized = False
            self.configured_pins.clear()
            self._active_pins.clear()
            logger.debug("✅ GPIO cleanup completado")
        except Exception as e:
            logger.error(f"❌ Error en GPIO cleanup: {e}")
    
    async def activate_pin(self, pin: int, duration: float, name: str = "", note: int = None):
        """
        Activa un pin GPIO (HIGH) durante un tiempo específico.
        
        Args:
            pin: Número de pin GPIO
            duration: Duración en segundos
            name: Nombre descriptivo del pin
            note: Número de nota MIDI que originó la activación
        """
        if not self.initialized:
            logger.error(f"❌ GPIO no inicializado, no se puede activar pin {pin}")
            return
        
        if pin not in self.configured_pins:
            logger.error(f"❌ Pin {pin} no está configurado")
            return
        
        if pin in self._active_pins:
            logger.debug(f"Pin {pin} ({name}) ya está activo - ignorando")
            return
        
        async with self._pin_locks.get(pin, asyncio.Lock()):
            try:
                pin_desc = f"{pin} ({name})" if name else str(pin)
                note_desc = f" - Nota {note}" if note is not None else ""
                
                self._active_pins.add(pin)
                
                start_time = time.time()
                if self.simulate:
                    logger.info(f"🔌 [SIM] GPIO {pin_desc}{note_desc}")
                else:
                    GPIO.output(pin, GPIO.HIGH)
                    logger.info(f"🔌 GPIO {pin_desc}{note_desc}")
                
                await asyncio.sleep(duration)
                
                actual_duration = time.time() - start_time
                if self.simulate:
                    logger.debug(f"🔌 [SIM] Pin {pin_desc} → LOW ({actual_duration:.3f}s)")
                else:
                    GPIO.output(pin, GPIO.LOW)
                    logger.debug(f"🔌 Pin {pin_desc} → LOW ({actual_duration:.3f}s)")
                
            except Exception as e:
                logger.error(f"❌ Error activando pin {pin}: {e}")
            finally:
                self._active_pins.discard(pin)
    
    def get_active_pins(self) -> Set[int]:
        """Retorna el conjunto de pines actualmente activos."""
        return self._active_pins.copy()
    
    def is_pin_active(self, pin: int) -> bool:
        """Retorna True si el pin está actualmente activo."""
        return pin in self._active_pins
