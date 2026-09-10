#!/usr/bin/env python3
"""
Orquestador de eventos del servidor MIDI.

Recibe eventos del cliente TCP y los procesa:
- Eventos NOTA: Programa activación de GPIO según configuración
- Eventos CC: Gestiona pantalla/animaciones con delay de 1 segundo
- Eventos START: Inicio de canción, detiene pantalla idle
- Eventos STOP/END: el corte se programa en ts+delay (el mismo reloj que
  las notas) para coincidir con el audio; un START posterior anula el corte.
"""
import logging
import time
from typing import Optional

import timing_log   # LOG TEMPORAL de timing (quitar tras depurar)

from config_loader import ConfigLoader
from scheduler import Scheduler
from gpio_executor import GPIOExecutor
from media_manager import MediaManager
from display_executor import DisplayExecutor
from status_screen import StatusScreenRunner

logger = logging.getLogger("cliente.orchestrator")

# Modos de pantalla (CC = carpeta, VALUE = subcarpeta dentro de /images/)
IDLE_CC           = 3  # Conectado, no reproduciendo  → 003/003
IDLE_VALUE        = 3
DISCONNECTED_CC   = 3  # Sin conexión al servidor     → 003/001
DISCONNECTED_VALUE = 1


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
        self.config = config
        self.scheduler = scheduler
        self.gpio_executor = gpio_executor
        self.media_manager = media_manager
        self.display_executor = display_executor
        self.base_delay_ms = base_delay_ms

        # Flags de configuración recibidos del servidor
        self._debug    = False  # True → pantalla de estado; False → animación idle
        self._ruido    = True   # False → no activar GPIO
        self._pantalla = True   # False → no actualizar display

        # Estado de conexión y reproducción
        self._connected = False  # True → conectado al servidor
        self._playing   = False  # True → reproduciendo una canción (entre START y STOP/END)
        # Generación de transporte: un START incrementa; el STOP/END diferido
        # no corta si ya arrancó otra canción (cambio de tema).
        self._transport_seq = 0

        # Bucle idle: el DisplayExecutor loopea solo (loop:true). Un hilo
        # que reencolaba play_animation cada ciclo dejaba comandos sueltos
        # que pintaban frames de ojos a mitad de la canción.
        self._idle_active = False

        self.current_bpm: float = 0.0

        self.stats = {
            'notas_recibidas': 0,
            'notas_mapeadas': 0,
            'notas_sin_mapeo': 0,
            'gpio_programados': 0,
            'cc_recibidos': 0,
            'stops_recibidos': 0,
            'tareas_canceladas': 0,
            'bpm_recibidos': 0,
        }

        # Crear runner de pantalla de estado
        self.status_runner = StatusScreenRunner(
            display_callback=self.display_executor.write_raw_frame,
            invertir=self.config.invertir
        )
        self._status_screen_active = False

        # Iniciar idle según modo (producción por defecto)
        logger.info("🤖 Iniciando pantalla idle...")
        self._show_idle()

    # ── Configuración ─────────────────────────────────────────────────────────

    def apply_config(self, debug: bool, ruido: bool, pantalla: bool):
        """Aplica la configuración recibida del servidor."""
        self._ruido    = ruido
        self._pantalla = pantalla
        if debug != self._debug:
            self._debug = debug
            # Si estamos en idle, cambiar la pantalla según el nuevo modo
            if not self._playing:
                self._show_idle()
        logger.info(f"⚙️  Config aplicada: debug={debug}, ruido={ruido}, pantalla={pantalla}")

    def set_connection_status(self, connected: bool, host: str = "", port: int = 0):
        """Actualiza el estado de conexión y cambia la animación idle si no se está reproduciendo."""
        self.status_runner.set_connection_status(connected, host, port)
        if connected != self._connected:
            self._connected = connected
            if not self._playing:
                self._show_idle()

    # ── Gestión de idle ───────────────────────────────────────────────────────

    def _show_idle(self):
        """Muestra la pantalla según el modo activo:
        - debug=True       → pantalla de estado
        - connected=True   → animación idle (003/003)
        - connected=False  → animación desconectado (003/001)
        """
        self._stop_production_idle()
        if self._debug:
            self.start_status_screen()
        elif self._connected:
            self._start_idle_animation(IDLE_CC, IDLE_VALUE, "idle")
        else:
            self._start_idle_animation(DISCONNECTED_CC, DISCONNECTED_VALUE, "desconectado")

    def _start_idle_animation(self, cc: int, value: int, mode_name: str):
        """Arranca la animación idle. El display la repite solo (loop)."""
        if not self._pantalla:
            return

        # Asegurar que la pantalla de estado está parada y el display corriendo
        if self._status_screen_active:
            self._status_screen_active = False
            self.status_runner.stop()
            self.display_executor.resume()

        anim_config = self.media_manager.get_animation(cc, value)
        if anim_config is None:
            logger.warning(
                f"⚠️  Animación {mode_name} {cc:03d}/{value:03d} "
                "no encontrada — usando pantalla de estado"
            )
            self.start_status_screen()
            return

        self._idle_active = True
        self.display_executor.play_animation(anim_config, source="idle")
        logger.info(f"🎬 Animación {mode_name} activa ({cc:03d}/{value:03d})")

    def _stop_production_idle(self):
        """Deja de considerar idle activo. El display ignora source=idle
        en cuanto set_live(True) (y vacía la cola de comandos)."""
        self._idle_active = False

    def start_status_screen(self):
        """Inicia la pantalla de estado (modo debug idle)."""
        if self._status_screen_active:
            return
        self.display_executor.pause()
        self.status_runner.start()
        self._status_screen_active = True
        logger.info("🤖 Pantalla de estado activa")

    def stop_status_screen(self):
        """Detiene la pantalla de estado."""
        if not self._status_screen_active:
            return
        self._status_screen_active = False
        self.status_runner.stop()
        self.display_executor.resume()

    # ── Handlers de eventos ───────────────────────────────────────────────────

    def handle_nota(self, server_ts_ms: int, note: int, channel: int, velocity: int):
        self.stats['notas_recibidas'] += 1

        # Visuales aunque la nota no tenga GPIO (bombo/caja de la partitura
        # MIDI). Si no, se oye el golpe y la pantalla no se entera.
        self._schedule_hit_visual(server_ts_ms, note, velocity)

        pins = self.config.get_pins_for_note(note)
        if not pins:
            self.stats['notas_sin_mapeo'] += 1
            logger.debug(f"Nota {note} sin mapeo GPIO - ignorando GPIO")
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

    def handle_caltest(self, server_ts_ms: int, pin: int):
        """Dispara UN pin como si fuera una nota: lo programa en
        server_ts + (base_delay - pin.delay), igual que handle_nota, para que
        la calibración use exactamente el mismo camino temporal que una
        canción (el sinte manda el ts con 1 s de adelanto). Ignora el flag
        `ruido`: calibrar implica querer oír/sentir el motor."""
        try:
            self._schedule_pin_activation(server_ts_ms, None, pin, force=True)
        except KeyError as e:
            logger.error(f"❌ CALTEST: pin {pin} no configurado: {e}")
        except Exception as e:
            logger.error(f"❌ CALTEST: error programando pin {pin}: {e}")

    def _schedule_pin_activation(self, server_ts_ms: int, note: int, pin: int,
                                 force: bool = False):
        """Programa la activación de un pin GPIO en el scheduler."""
        if not self._ruido and not force:
            logger.debug(f"GPIO desactivado (ruido=False) — omitiendo pin {pin}")
            return

        pin_config = self.config.get_pin_config(pin)
        adjusted_delay_ms = self.config.calculate_execution_delay(pin, self.base_delay_ms)
        execution_time_ms = server_ts_ms + adjusted_delay_ms

        now_ms = int(time.time() * 1000)
        delta_ms = execution_time_ms - now_ms

        logger.debug(
            f"   📌 Pin {pin} ({pin_config.nombre}): "
            f"delay={pin_config.delay}ms → ejecutar en {delta_ms:.1f}ms"
        )

        timing_log.log("sched", pin=pin, note=note, server_ts=server_ts_ms,
                       exec=execution_time_ms, pin_delay=pin_config.delay,
                       tiempo=pin_config.tiempo, force=force)  # LOG TEMPORAL
        self.scheduler.schedule_at_walltime(
            wall_time_ms=execution_time_ms,
            callback=self.gpio_executor.activate_pin,
            args=(pin, pin_config.tiempo, pin_config.nombre, note),
            description=f"GPIO {pin} ({pin_config.nombre}) - Nota {note}"
        )
        self.stats['gpio_programados'] += 1

    def _hit_kinds_for_note(self, note: int) -> list:
        """Bombo/caja/crash a partir de los pines, o de la nota MIDI."""
        kinds = []
        pins = self.config.get_pins_for_note(note)
        if pins:
            blob = " ".join(
                self.config.get_pin_config(p).nombre.lower() for p in pins)
            if "bombo" in blob:
                kinds.append("kick")
            if "caja" in blob:
                kinds.append("snare")
            if "crash" in blob or "platillo" in blob:
                kinds.append("crash")
        if kinds:
            return kinds
        # Fallback: mismas notas que NOTAS.md / cliente.maleta.json
        if note in (36, 39, 41, 42, 62, 64, 66, 70):
            kinds.append("kick")
        if note in (37, 38, 39, 43, 63, 64, 65, 67, 71):
            kinds.append("snare")
        if note in (40, 42, 43, 66, 67, 72):
            kinds.append("crash")
        return kinds

    def _schedule_hit_visual(self, server_ts_ms: int, note: int, velocity: int):
        """Encola impulsos de escena al mismo reloj que las imágenes (ts+1s)."""
        if not self._pantalla:
            return
        kinds = self._hit_kinds_for_note(note)
        if not kinds:
            return
        execution_time_ms = server_ts_ms + self.base_delay_ms
        for kind in kinds:
            self.scheduler.schedule_at_walltime(
                wall_time_ms=execution_time_ms,
                callback=self.display_executor.pulse_hit,
                args=(kind, velocity),
                description=f"HIT {kind} nota {note}"
            )

    def handle_cc(self, server_ts_ms: int, value: int, channel: int, controller: int):
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
        if not self._pantalla or not self._playing:
            return
        try:
            self.display_executor.play_animation(anim_config)
            logger.info(f"✅ Animación reproducida: CC {cc:03d}/{value:03d}")
        except Exception as e:
            logger.error(f"❌ Error reproduciendo animación {cc:03d}/{value:03d}: {e}")

    def _execute_image(self, image_data: bytes, cc: int, value: int):
        if not self._pantalla or not self._playing:
            return
        try:
            self.display_executor.show_image(image_data, cc, value)
            logger.info(f"✅ Imagen mostrada: CC {cc:03d}/{value:03d}")
        except Exception as e:
            logger.error(f"❌ Error mostrando imagen {cc:03d}/{value:03d}: {e}")

    def _execute_scene(self, name: str):
        if not self._pantalla or not self._playing:
            return
        try:
            self._stop_production_idle()
            if self._status_screen_active:
                self.stop_status_screen()
            self.display_executor.play_scene(name)
            logger.info(f"✅ Escena procedural: {name}")
        except Exception as e:
            logger.error(f"❌ Error activando escena {name}: {e}")

    def handle_start(self, server_ts_ms: int):
        logger.info(f"▶️  START recibido (ts={server_ts_ms}) - Iniciando canción")
        self._transport_seq += 1
        self._playing = True
        self._stop_production_idle()
        if self._status_screen_active:
            self.stop_status_screen()
        self.display_executor.set_live(True)
        # Escena live al mismo reloj que el audio. Sin MDCC en la canción.
        if self._pantalla:
            if self.current_bpm > 0:
                self.display_executor.set_bpm(self.current_bpm)
            execution_time_ms = server_ts_ms + self.base_delay_ms
            self.scheduler.schedule_at_walltime(
                wall_time_ms=execution_time_ms,
                callback=self._execute_scene,
                args=("live",),
                description="Escena live"
            )

    def handle_stop(self, server_ts_ms: int):
        self.stats['stops_recibidos'] += 1
        self._schedule_transport_end(server_ts_ms, "STOP")

    def handle_bpm(self, server_ts_ms: int, bpm: float):
        self.current_bpm = bpm
        self.stats['bpm_recibidos'] += 1
        logger.info(f"🎵 BPM: {bpm:.2f}")
        execution_time_ms = server_ts_ms + self.base_delay_ms
        self.scheduler.schedule_at_walltime(
            wall_time_ms=execution_time_ms,
            callback=self.display_executor.set_bpm,
            args=(bpm,),
            description=f"BPM {bpm:.1f}"
        )

    def handle_end(self, server_ts_ms: int):
        self._schedule_transport_end(server_ts_ms, "END")

    def _schedule_transport_end(self, server_ts_ms: int, kind: str):
        """Corta en ts+delay, al mismo instante audible que las notas.

        Si se aplica al recibir, la maleta se apaga ~1 s antes que el audio
        (el secuenciador va por delante) y se tiran los golpes ya encolados.
        Un START posterior incrementa `_transport_seq` y este corte no corre.
        """
        seq = self._transport_seq
        execution_time_ms = server_ts_ms + self.base_delay_ms
        self.scheduler.schedule_at_walltime(
            wall_time_ms=execution_time_ms,
            callback=self._apply_transport_end,
            args=(seq, kind),
            description=kind,
        )
        logger.info(
            f"⏹️  {kind} recibido (ts={server_ts_ms}) — "
            f"corte en {self.base_delay_ms}ms"
        )

    def _apply_transport_end(self, seq: int, kind: str):
        if seq != self._transport_seq:
            logger.info(f"⏭️  {kind} anulado (ya hay START nuevo)")
            return
        cancelled = self.scheduler.clear_queue()
        self.stats['tareas_canceladas'] += cancelled
        logger.info(
            f"⏹️  {kind} — cola limpiada: {cancelled} eventos cancelados"
        )
        self._playing = False
        self.display_executor.set_live(False)
        self._show_idle()

    def cleanup(self):
        self._stop_production_idle()
        if self._status_screen_active:
            self.status_runner.stop()

    def get_stats(self) -> dict:
        return self.stats.copy()

    def print_stats(self):
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
