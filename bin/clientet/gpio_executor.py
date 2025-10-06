#!/usr/bin/env python3
"""
Ejecutor de acciones GPIO con timing preciso.

Gestiona la activación de pines GPIO:
- Inicializa los pines según configuración
- Activa pines (HIGH) por un tiempo específico
- Desactiva automáticamente (LOW)
- Maneja múltiples pines concurrentemente
- Cleanup al finalizar
"""
import asyncio
import logging
from typing import Set
import time

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    logging.warning("RPi.GPIO no disponible - modo simulación")

logger = logging.getLogger("clientet.gpio")


class GPIOExecutor:
    """
    Ejecutor de acciones GPIO con soporte para activaciones temporales.
    
    Si RPi.GPIO no está disponible, funciona en modo simulación (solo logging).
    """
    
    def __init__(self, simulate: bool = None):
        """
        Args:
            simulate: Si True, simula GPIO sin hardware real.
                     Si None, detecta automáticamente (True si RPi.GPIO no disponible)
        """
        if simulate is None:
            simulate = not GPIO_AVAILABLE
        
        self.simulate = simulate
        self.initialized = False
        self.configured_pins: Set[int] = set()
        self._active_pins: Set[int] = set()  # Pines actualmente en HIGH
        self._pin_locks = {}  # Locks por pin para evitar conflictos
    
    def initialize(self, pins: list[int]):
        """
        Inicializa los pines GPIO.
        
        Args:
            pins: Lista de números de pin GPIO a configurar
        """
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
        Activa un pin GPIO (HIGH) durante un tiempo específico, luego lo desactiva (LOW).
        
        Si el pin ya está activo, esta llamada se ignora (no extiende el tiempo).
        
        Args:
            pin: Número de pin GPIO
            duration: Duración en segundos que el pin debe estar HIGH
            name: Nombre descriptivo del pin para logging
            note: Número de nota MIDI que originó la activación (opcional, para logging)
        """
        if not self.initialized:
            logger.error(f"❌ GPIO no inicializado, no se puede activar pin {pin}")
            return
        
        if pin not in self.configured_pins:
            logger.error(f"❌ Pin {pin} no está configurado")
            return
        
        # Verificar si el pin ya está activo
        if pin in self._active_pins:
            logger.debug(f"Pin {pin} ({name}) ya está activo - ignorando nueva activación")
            return
        
        # Adquirir lock del pin (aunque con la comprobación anterior no debería ser necesario)
        async with self._pin_locks.get(pin, asyncio.Lock()):
            try:
                pin_desc = f"{pin} ({name})" if name else str(pin)
                note_desc = f" - Nota {note}" if note is not None else ""
                
                # Marcar como activo
                self._active_pins.add(pin)
                
                # Activar (HIGH)
                start_time = time.time()
                if self.simulate:
                    logger.info(f"🔌 [SIM] GPIO {pin_desc}{note_desc}")
                else:
                    GPIO.output(pin, GPIO.HIGH)
                    logger.info(f"🔌 GPIO {pin_desc}{note_desc}")
                
                # Esperar el tiempo especificado
                await asyncio.sleep(duration)
                
                # Desactivar (LOW)
                actual_duration = time.time() - start_time
                if self.simulate:
                    logger.debug(f"🔌 [SIM] Pin {pin_desc} → LOW (estuvo {actual_duration:.3f}s)")
                else:
                    GPIO.output(pin, GPIO.LOW)
                    logger.debug(f"🔌 Pin {pin_desc} → LOW (estuvo {actual_duration:.3f}s)")
                
            except Exception as e:
                logger.error(f"❌ Error activando pin {pin}: {e}")
            finally:
                # Siempre marcar como inactivo al terminar
                self._active_pins.discard(pin)
    
    def get_active_pins(self) -> Set[int]:
        """Retorna el conjunto de pines actualmente activos (en HIGH)."""
        return self._active_pins.copy()
    
    def is_pin_active(self, pin: int) -> bool:
        """Retorna True si el pin está actualmente activo (HIGH)."""
        return pin in self._active_pins


if __name__ == '__main__':
    # Test del ejecutor GPIO
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s.%(msecs)03d %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    async def test_gpio():
        executor = GPIOExecutor(simulate=True)
        
        logger.info("\n" + "="*60)
        logger.info("Test del GPIO Executor")
        logger.info("="*60)
        
        # Inicializar algunos pines
        executor.initialize([23, 17, 27, 22])
        
        # Activar varios pines concurrentemente
        tasks = [
            executor.activate_pin(23, 0.15, "Bombo"),
            executor.activate_pin(17, 0.05, "Caja1"),
            executor.activate_pin(27, 0.05, "Caja2"),
        ]
        
        # Esperar a que terminen
        await asyncio.gather(*tasks)
        
        # Intentar activar el mismo pin dos veces
        logger.info("\n--- Test: activación doble del mismo pin ---")
        task1 = asyncio.create_task(executor.activate_pin(22, 0.2, "Platillo"))
        await asyncio.sleep(0.05)  # Esperar un poco
        task2 = asyncio.create_task(executor.activate_pin(22, 0.2, "Platillo"))  # Debería ignorarse
        await asyncio.gather(task1, task2)
        
        # Cleanup
        executor.cleanup()
        logger.info("Test completado")
    
    asyncio.run(test_gpio())
