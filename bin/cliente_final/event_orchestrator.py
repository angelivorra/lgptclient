#!/usr/bin/env python3
"""
Orquestador de eventos del servidor MIDI.

Recibe eventos del cliente TCP y los procesa:
- Eventos NOTA: Programa activación de GPIO según configuración
- Eventos CC: Gestiona pantalla/animaciones con delay de 1 segundo
- Eventos START: Inicio de canción, detiene pantalla de estado
- Eventos STOP: Limpia cola de eventos pendientes, muestra pantalla de estado
- Eventos END: Fin de canción, vuelve a pantalla de estado
"""
import logging
import time
from typing import Optional

from config_loader import ConfigLoader
from scheduler import Scheduler
from gpio_executor import GPIOExecutor
from media_manager import MediaManager
from display_executor import DisplayExecutor
from status_screen import StatusScreenRunner

logger = logging.getLogger("cliente.orchestrator")


class EventOrchestrator:
    """Orquesta eventos del servidor y programa ejecuciones de GPIO y display."""
    
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
        
        self.stats = {
            'notas_recibidas': 0,
            'notas_mapeadas': 0,
            'notas_sin_mapeo': 0,
            'gpio_programados': 0,
            'cc_recibidos': 0,
            'stops_recibidos': 0,
            'tareas_canceladas': 0,
        }
        
        # Crear runner de pantalla de estado
        self.status_runner = StatusScreenRunner(
            display_callback=self.display_executor.write_raw_frame,
            invertir=self.config.invertir
        )
        self._status_screen_active = False
        
        # Iniciar pantalla de estado
        logger.info("🤖 Iniciando pantalla de estado...")
        self.start_status_screen()
    
    def set_connection_status(self, connected: bool, host: str = "", port: int = 0):
        """
        Actualiza el estado de conexión en la pantalla de estado.
        
        Args:
            connected: True si está conectado al servidor
            host: Host del servidor
            port: Puerto del servidor
        """
        self.status_runner.set_connection_status(connected, host, port)
    
    def start_status_screen(self):
        """Inicia la pantalla de estado (modo idle)."""
        if self._status_screen_active:
            return
        
        # Pausar el display executor normal
        self.display_executor.pause()
        
        # Iniciar pantalla de estado
        self.status_runner.start()
        self._status_screen_active = True
        logger.info("🤖 Pantalla de estado activa")
    
    def stop_status_screen(self):
        """Detiene la pantalla de estado (para mostrar contenido real)."""
        if not self._status_screen_active:
            return
        
        # Marcar como inactiva PRIMERO para evitar re-entrancia
        self._status_screen_active = False
        
        # Detener pantalla de estado (no bloqueante)
        self.status_runner.stop()
        
        # Resumir el display executor normal
        self.display_executor.resume()
    
    def handle_nota(self, server_ts_ms: int, note: int, channel: int, velocity: int):
        """
        Procesa un evento NOTA del servidor.
        
        Args:
            server_ts_ms: Timestamp del servidor en milisegundos
            note: Número de nota MIDI (0-127)
            channel: Canal MIDI
            velocity: Velocidad de la nota
        """
        self.stats['notas_recibidas'] += 1
        
        pins = self.config.get_pins_for_note(note)
        
        if not pins:
            self.stats['notas_sin_mapeo'] += 1
            logger.debug(f"Nota {note} sin mapeo GPIO - ignorando")
            return
        
        self.stats['notas_mapeadas'] += 1
        logger.debug(f"🎵 NOTA {note} → {len(pins)} pin(es): {pins}")
        
        for pin in pins:
            try:
                self._schedule_pin_activation(server_ts_ms, note, pin)
            except KeyError as e:
                logger.error(f"❌ Pin {pin} no configurado: {e}")
            except Exception as e:
                logger.error(f"❌ Error programando pin {pin}: {e}")
    
    def _schedule_pin_activation(self, server_ts_ms: int, note: int, pin: int):
        """Programa la activación de un pin GPIO en el scheduler."""
        pin_config = self.config.get_pin_config(pin)
        
        adjusted_delay_ms = self.config.calculate_execution_delay(pin, self.base_delay_ms)
        execution_time_ms = server_ts_ms + adjusted_delay_ms
        
        now_ms = int(time.time() * 1000)
        delta_ms = execution_time_ms - now_ms
        
        logger.debug(
            f"   📌 Pin {pin} ({pin_config.nombre}): "
            f"delay={pin_config.delay}ms → ejecutar en {delta_ms:.1f}ms"
        )
        
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
            server_ts_ms: Timestamp del servidor en milisegundos
            value: Valor del controlador (0-127)
            channel: Canal MIDI
            controller: Número de controlador CC
        """
        self.stats['cc_recibidos'] += 1
        
        cc = controller
        logger.debug(f"🎛️  CC {cc}={value} (canal {channel})")
        
        is_animation = self.media_manager.is_animation(cc, value)
        
        if is_animation:
            anim_config = self.media_manager.get_animation(cc, value)
            if anim_config is None:
                logger.warning(f"⚠️  Animación CC {cc}/{value} no encontrada")
                return
            
            logger.debug(f"   🎬 Animación {cc:03d}/{value:03d} precargada")
            
            execution_time_ms = server_ts_ms + self.base_delay_ms
            
            self.scheduler.schedule_at_walltime(
                wall_time_ms=execution_time_ms,
                callback=self._execute_animation,
                args=(anim_config, cc, value),
                description=f"Animación {cc:03d}/{value:03d}"
            )
            
        else:
            image_data = self.media_manager.get_image(cc, value)
            if image_data is None:
                logger.warning(f"⚠️  Imagen CC {cc}/{value} no encontrada")
                return
            
            logger.debug(f"   🖼️  Imagen {cc:03d}/{value:03d} precargada")
            
            execution_time_ms = server_ts_ms + self.base_delay_ms
            
            self.scheduler.schedule_at_walltime(
                wall_time_ms=execution_time_ms,
                callback=self._execute_image,
                args=(image_data, cc, value),
                description=f"Imagen {cc:03d}/{value:03d}"
            )
        
        now_ms = int(time.time() * 1000)
        delta_ms = (server_ts_ms + self.base_delay_ms) - now_ms
        logger.debug(f"   ⏰ Programado para ejecutar en {delta_ms:.1f}ms")
    
    def _execute_animation(self, anim_config, cc: int, value: int):
        """Callback para ejecutar una animación."""
        try:
            self.display_executor.play_animation(anim_config)
            logger.info(f"✅ Animación reproducida: CC {cc:03d}/{value:03d}")
        except Exception as e:
            logger.error(f"❌ Error reproduciendo animación {cc:03d}/{value:03d}: {e}")
    
    def _execute_image(self, image_data: bytes, cc: int, value: int):
        """Callback para mostrar una imagen."""
        try:
            self.display_executor.show_image(image_data, cc, value)
            logger.info(f"✅ Imagen mostrada: CC {cc:03d}/{value:03d}")
        except Exception as e:
            logger.error(f"❌ Error mostrando imagen {cc:03d}/{value:03d}: {e}")
    
    def handle_start(self, server_ts_ms: int):
        """Procesa un evento START del servidor."""
        logger.info(f"▶️  START recibido (ts={server_ts_ms}) - Iniciando canción")
        
        # Detener pantalla de estado para mostrar contenido
        if self._status_screen_active:
            self.stop_status_screen()
    
    def handle_stop(self, server_ts_ms: int):
        """
        Procesa un evento STOP del servidor.
        Limpia la cola de eventos futuros programados.
        """
        self.stats['stops_recibidos'] += 1
        
        # Limpiar cola de eventos pendientes
        cancelled = self.scheduler.clear_queue()
        self.stats['tareas_canceladas'] += cancelled
        
        logger.info(
            f"⏹️  STOP recibido (ts={server_ts_ms}) - "
            f"Cola limpiada: {cancelled} eventos cancelados"
        )
        
        # Volver a pantalla de estado
        self.start_status_screen()
    
    def handle_end(self, server_ts_ms: int):
        """Procesa un evento END del servidor."""
        logger.info(f"⏹️  END recibido (ts={server_ts_ms}) - Canción terminada")
        
        # Volver a pantalla de estado
        self.start_status_screen()
    
    def cleanup(self):
        """Limpia recursos del orquestador."""
        if self._status_screen_active:
            self.status_runner.stop()
    
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
        logger.info(f"STOPs recibidos:     {self.stats['stops_recibidos']}")
        logger.info(f"Tareas canceladas:   {self.stats['tareas_canceladas']}")
        logger.info("="*60)
