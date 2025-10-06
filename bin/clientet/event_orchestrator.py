#!/usr/bin/env python3
"""
Orquestador de eventos del servidor MIDI.

Recibe eventos del cliente TCP y los procesa:
- Eventos NOTA: Programa activación de GPIO según configuración
- Eventos CC: Gestiona pantalla/animaciones con delay de 1 segundo
- Eventos START/END: (Futuro) Control de secuencia

Para cada evento NOTA:
1. Busca qué pines GPIO activar según la nota
2. Para cada pin, calcula el tiempo de ejecución ajustado por su delay
3. Programa la tarea en el scheduler

Para cada evento CC:
1. Precarga la imagen/animación en memoria si es posible
2. Programa su reproducción 1 segundo después
"""
import logging
import time
from typing import Optional

from config_loader import ConfigLoader
from scheduler import Scheduler
from gpio_executor import GPIOExecutor
from media_manager import MediaManager
from display_executor import DisplayExecutor

logger = logging.getLogger("clientet.orchestrator")


class EventOrchestrator:
    """
    Orquesta eventos del servidor y programa ejecuciones de GPIO y display.
    """
    
    def __init__(
        self,
        config: ConfigLoader,
        scheduler: Scheduler,
        gpio_executor: GPIOExecutor,
        media_manager: MediaManager,
        display_executor: DisplayExecutor,
        base_delay_ms: int = 1000
    ):
        """
        Args:
            config: Configuración de instrumentos y pines
            scheduler: Scheduler para programar tareas
            gpio_executor: Ejecutor de GPIO
            media_manager: Gestor de imágenes y animaciones
            display_executor: Ejecutor de display
            base_delay_ms: Delay base en milisegundos (default: 1 segundo)
        """
        self.config = config
        self.scheduler = scheduler
        self.gpio_executor = gpio_executor
        self.media_manager = media_manager
        self.display_executor = display_executor
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
        
        Precarga la imagen/animación y programa su reproducción 1 segundo después.
        
        Args:
            server_ts_ms: Timestamp del servidor en milisegundos
            value: Valor del controlador (0-127)
            channel: Canal MIDI (ignorado)
            controller: Número de controlador CC
        """
        self.stats['cc_recibidos'] += 1
        
        cc = controller
        
        logger.debug(f"🎛️  CC {cc}={value} (canal {channel})")
        
        # Verificar si es animación o imagen
        is_animation = self.media_manager.is_animation(cc, value)
        
        if is_animation:
            # Pre-cargar configuración de animación
            anim_config = self.media_manager.get_animation(cc, value)
            if anim_config is None:
                logger.warning(f"⚠️  Animación CC {cc}/{value} no encontrada")
                return
            
            logger.debug(f"   🎬 Animación {cc:03d}/{value:03d} precargada")
            
            # Programar reproducción en 1 segundo
            execution_time_ms = server_ts_ms + self.base_delay_ms
            
            self.scheduler.schedule_at_walltime(
                wall_time_ms=execution_time_ms,
                callback=self._execute_animation,
                args=(anim_config, cc, value),
                description=f"Animación {cc:03d}/{value:03d}"
            )
            
        else:
            # Pre-cargar imagen en cache
            image_data = self.media_manager.get_image(cc, value)
            if image_data is None:
                logger.warning(f"⚠️  Imagen CC {cc}/{value} no encontrada")
                return
            
            logger.debug(f"   🖼️  Imagen {cc:03d}/{value:03d} precargada en cache")
            
            # Programar mostrar en 1 segundo
            execution_time_ms = server_ts_ms + self.base_delay_ms
            
            self.scheduler.schedule_at_walltime(
                wall_time_ms=execution_time_ms,
                callback=self._execute_image,
                args=(image_data, cc, value),
                description=f"Imagen {cc:03d}/{value:03d}"
            )
        
        # Calcular delta para logging
        now_ms = int(time.time() * 1000)
        delta_ms = (server_ts_ms + self.base_delay_ms) - now_ms
        logger.debug(f"   ⏰ Programado para ejecutar en {delta_ms:.1f}ms")
    
    def _execute_animation(self, anim_config, cc: int, value: int):
        """
        Callback para ejecutar una animación (llamado por el scheduler).
        
        Args:
            anim_config: Configuración de la animación
            cc: Control change
            value: Valor
        """
        try:
            self.display_executor.play_animation(anim_config)
            logger.info(f"✅ Animación reproducida: CC {cc:03d}/{value:03d}")
        except Exception as e:
            logger.error(f"❌ Error reproduciendo animación {cc:03d}/{value:03d}: {e}")
    
    def _execute_image(self, image_data: bytes, cc: int, value: int):
        """
        Callback para mostrar una imagen (llamado por el scheduler).
        
        Args:
            image_data: Datos binarios de la imagen
            cc: Control change
            value: Valor
        """
        try:
            self.display_executor.show_image(image_data, cc, value)
            logger.info(f"✅ Imagen mostrada: CC {cc:03d}/{value:03d}")
        except Exception as e:
            logger.error(f"❌ Error mostrando imagen {cc:03d}/{value:03d}: {e}")
    
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
    import os
    
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
        
        # Crear media manager y display executor
        base_path = "/home/angel/images"
        media_manager = MediaManager(base_path)
        display_executor = DisplayExecutor(simulate=True)
        
        # Crear orchestrator
        orchestrator = EventOrchestrator(
            config, 
            scheduler, 
            gpio_executor,
            media_manager,
            display_executor,
            base_delay_ms=500  # 500ms para test más rápido
        )
        
        logger.info("\n" + "="*60)
        logger.info("Test del Event Orchestrator")
        logger.info("="*60)
        
        # Simular algunos eventos
        current_ts = int(time.time() * 1000)
        
        logger.info("\n--- Evento 1: Nota 36 (Bombo) ---")
        orchestrator.handle_nota(current_ts, 36, 0, 127)
        
        await asyncio.sleep(0.2)
        
        logger.info("\n--- Evento 2: Imagen CC 2/3 ---")
        orchestrator.handle_cc(current_ts + 200, 3, 0, 2)
        
        await asyncio.sleep(0.2)
        
        logger.info("\n--- Evento 3: Animación CC 3/1 ---")
        orchestrator.handle_cc(current_ts + 400, 1, 0, 3)
        
        # Esperar a que se ejecuten
        await asyncio.sleep(2)
        
        # Mostrar estadísticas
        orchestrator.print_stats()
        media_manager.print_stats()
        display_executor.print_stats()
        
        # Cleanup
        await scheduler.stop()
        gpio_executor.cleanup()
        display_executor.cleanup()
        
        logger.info("\nTest completado")
    
    asyncio.run(test_orchestrator())
