#!/usr/bin/env python3
"""
Orquestador de eventos del servidor MIDI.

Recibe eventos del cliente TCP y los procesa:
- Eventos NOTA: Programa activación de GPIO según configuración
- Eventos CC: (Futuro) Gestiona pantalla/animaciones
- Eventos START/END: (Futuro) Control de secuencia

Para cada evento NOTA:
1. Busca qué pines GPIO activar según la nota
2. Para cada pin, calcula el tiempo de ejecución ajustado por su delay
3. Programa la tarea en el scheduler
"""
import logging
import time
from typing import Optional

from config_loader import ConfigLoader
from scheduler import Scheduler
from gpio_executor import GPIOExecutor

logger = logging.getLogger("clientet.orchestrator")


class EventOrchestrator:
    """
    Orquesta eventos del servidor y programa ejecuciones de GPIO.
    """
    
    def __init__(
        self,
        config: ConfigLoader,
        scheduler: Scheduler,
        gpio_executor: GPIOExecutor,
        base_delay_ms: int = 1000
    ):
        """
        Args:
            config: Configuración de instrumentos y pines
            scheduler: Scheduler para programar tareas
            gpio_executor: Ejecutor de GPIO
            base_delay_ms: Delay base en milisegundos (default: 1 segundo)
        """
        self.config = config
        self.scheduler = scheduler
        self.gpio_executor = gpio_executor
        self.base_delay_ms = base_delay_ms
        
        # Estadísticas
        self.stats = {
            'notas_recibidas': 0,
            'notas_mapeadas': 0,
            'notas_sin_mapeo': 0,
            'gpio_programados': 0,
            'cc_recibidos': 0,
        }
    
    def handle_nota(self, server_ts_ms: int, note: int, channel: int, velocity: int):
        """
        Procesa un evento NOTA del servidor.
        
        Args:
            server_ts_ms: Timestamp del servidor en milisegundos
            note: Número de nota MIDI (0-127)
            channel: Canal MIDI
            velocity: Velocidad de la nota (ignorada)
        """
        self.stats['notas_recibidas'] += 1
        
        # Buscar pines asociados a esta nota
        pins = self.config.get_pins_for_note(note)
        
        if not pins:
            self.stats['notas_sin_mapeo'] += 1
            logger.debug(f"Nota {note} sin mapeo GPIO - ignorando")
            return
        
        self.stats['notas_mapeadas'] += 1
        logger.debug(f"🎵 NOTA {note} → {len(pins)} pin(es): {pins}")
        
        # Programar activación de cada pin
        for pin in pins:
            try:
                self._schedule_pin_activation(server_ts_ms, note, pin)
            except KeyError as e:
                logger.error(f"❌ Pin {pin} no configurado: {e}")
            except Exception as e:
                logger.error(f"❌ Error programando pin {pin}: {e}")
    
    def _schedule_pin_activation(self, server_ts_ms: int, note: int, pin: int):
        """
        Programa la activación de un pin GPIO en el scheduler.
        
        Args:
            server_ts_ms: Timestamp del servidor
            note: Nota MIDI que originó la activación
            pin: Pin GPIO a activar
        """
        # Obtener configuración del pin
        pin_config = self.config.get_pin_config(pin)
        
        # Calcular tiempo de ejecución ajustado
        # Formula: execution_time = server_timestamp + base_delay - pin_delay
        adjusted_delay_ms = self.config.calculate_execution_delay(pin, self.base_delay_ms)
        execution_time_ms = server_ts_ms + adjusted_delay_ms
        
        # Calcular delta desde ahora (para logging)
        now_ms = int(time.time() * 1000)
        delta_ms = execution_time_ms - now_ms
        
        logger.debug(
            f"   📌 Pin {pin} ({pin_config.nombre}): "
            f"delay={pin_config.delay}ms → ejecutar en {delta_ms:.1f}ms "
            f"(activo {pin_config.tiempo:.3f}s)"
        )
        
        # Programar en el scheduler (incluyendo el número de nota para logging)
        self.scheduler.schedule_at_walltime(
            wall_time_ms=execution_time_ms,
            callback=self.gpio_executor.activate_pin,
            args=(pin, pin_config.tiempo, pin_config.nombre, note),
            description=f"GPIO {pin} ({pin_config.nombre}) - Nota {note}"
        )
        
        self.stats['gpio_programados'] += 1
    
    def handle_cc(self, server_ts_ms: int, value: int, channel: int, controller: int):
        """
        Procesa un evento CC (Control Change) del servidor.
        
        Args:
            server_ts_ms: Timestamp del servidor
            value: Valor del controlador
            channel: Canal MIDI
            controller: Número de controlador
        """
        self.stats['cc_recibidos'] += 1
        logger.debug(f"🎛️  CC {controller}={value} (canal {channel}) - No implementado")
        # TODO: Implementar gestión de pantalla/animaciones
    
    def handle_start(self, server_ts_ms: int):
        """Procesa un evento START del servidor."""
        logger.debug(f"▶️  START recibido (ts={server_ts_ms})")
    
    def handle_end(self, server_ts_ms: int):
        """Procesa un evento END del servidor."""
        logger.debug(f"⏹️  END recibido (ts={server_ts_ms})")
    
    def get_stats(self) -> dict:
        """Retorna estadísticas de eventos procesados."""
        return self.stats.copy()
    
    def print_stats(self):
        """Imprime estadísticas de forma legible."""
        logger.info("\n" + "="*60)
        logger.info("📊 Estadísticas del Orchestrator")
        logger.info("="*60)
        logger.info(f"Notas recibidas:     {self.stats['notas_recibidas']}")
        logger.info(f"  - Con mapeo:       {self.stats['notas_mapeadas']}")
        logger.info(f"  - Sin mapeo:       {self.stats['notas_sin_mapeo']}")
        logger.info(f"GPIO programados:    {self.stats['gpio_programados']}")
        logger.info(f"CC recibidos:        {self.stats['cc_recibidos']}")
        logger.info("="*60)


if __name__ == '__main__':
    # Test del orchestrator
    import asyncio
    
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s.%(msecs)03d %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    async def test_orchestrator():
        # Cargar config
        config = ConfigLoader()
        
        # Crear scheduler y GPIO executor
        scheduler = Scheduler()
        await scheduler.start()
        
        gpio_executor = GPIOExecutor(simulate=True)
        gpio_executor.initialize(config.get_all_pins())
        
        # Crear orchestrator
        orchestrator = EventOrchestrator(config, scheduler, gpio_executor)
        
        logger.info("\n" + "="*60)
        logger.info("Test del Event Orchestrator")
        logger.info("="*60)
        
        # Simular algunos eventos
        current_ts = int(time.time() * 1000)
        
        logger.info("\n--- Evento 1: Nota 36 (Bombo) ---")
        orchestrator.handle_nota(current_ts, 36, 0, 127)
        
        await asyncio.sleep(0.2)
        
        logger.info("\n--- Evento 2: Nota 39 (múltiples pines) ---")
        orchestrator.handle_nota(current_ts + 500, 39, 0, 127)
        
        await asyncio.sleep(0.2)
        
        logger.info("\n--- Evento 3: Nota sin mapeo ---")
        orchestrator.handle_nota(current_ts + 800, 99, 0, 127)
        
        # Esperar a que se ejecuten
        await asyncio.sleep(2)
        
        # Mostrar estadísticas
        orchestrator.print_stats()
        
        # Cleanup
        await scheduler.stop()
        gpio_executor.cleanup()
        
        logger.info("\nTest completado")
    
    asyncio.run(test_orchestrator())
