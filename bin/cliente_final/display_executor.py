#!/usr/bin/env python3
"""
Ejecutor de display para imágenes y animaciones en framebuffer.

Características:
- Un solo thread para gestionar todo el display (30 FPS sistema)
- Animaciones a 20 FPS
- Animaciones con loop y delay aleatorio entre repeticiones
- Cambio instantáneo entre imágenes y animaciones
"""
import time
import random
import logging
import threading
import queue
from typing import Optional

import numpy as np

from media_manager import AnimationConfig
from ribbon import BPM_CURVE, FondoRibbon, overlay_block_cols
from scenes import HEIGHT, WIDTH, SceneEngine
from fade_black import FadeBlack
from spark_hit import SPARK_CC, SPARK_VALUE, SparkHit
from vocoder_neon import VocoderNeon

logger = logging.getLogger("cliente.display")

SYSTEM_FPS = 30
FRAME_INTERVAL = 1.0 / SYSTEM_FPS

# Ojos de idle (images/003/003). El clip es un solo parpadeo a fps fijo;
# el ritmo vivo se arma aquí, no en el pack. El desconectado (003/001)
# sigue el max_delay de su anim.cfg.
IDLE_EYES_CC = 3
IDLE_EYES_VALUE = 3
# Pads sampler (sample1..4) en pausa: enfadado, contento, corazones, triste.
# El sinte emite estos valores por CC 3; ver midi_control.idle_pad_gesture.
IDLE_PAD_VALUES = (14, 15, 16, 17)

# Fondo slideshow: segundos por frame al tempo base de la canción (knob de
# tempo abajo) y exponente con el que el knob acelera (interval / ratio**N).
# Con TEMPO_BOOST_MAX=0.12 del sinte: 1.12**8 ≈ 2.5x → ~0.031 s/frame arriba,
# justo el ritmo del render (30 FPS); más rápido ya se saltaría frames.
FONDO_BASE_INTERVAL = 0.076
FONDO_BPM_CURVE = BPM_CURVE  # también la usa la línea (ribbon.speed_px_s)
# Imagen estática durante una canción: se ve un rato y vuelve al plasma.
IMAGE_HOLD_S = 2.0
# Bombo: temblor sobre el frame ya compuesto (fondo + letra). Barato: roll.
SHAKE_HALF_LIFE_S = 0.11
SHAKE_MAX_PX = 8


def shake_rgb565(frame: bytes, dx: int, dy: int,
                 width: int = WIDTH, height: int = HEIGHT) -> bytes:
    """Desplaza el frame; el borde que entra es negro (no wrap)."""
    if (not dx and not dy) or len(frame) != width * height * 2:
        return frame
    arr = np.frombuffer(frame, dtype="<u2").reshape(height, width)
    out = np.roll(arr, (dy, dx), axis=(0, 1))
    if dy > 0:
        out[:dy, :] = 0
    elif dy < 0:
        out[dy:, :] = 0
    if dx > 0:
        out[:, :dx] = 0
    elif dx < 0:
        out[:, dx:] = 0
    return out.astype("<u2").tobytes()


def idle_blink_gap() -> float:
    """Segundos quieto entre parpadeos.

    No es un uniforme de 1–5 s: a veces el segundo parpadeo va pegado,
    a veces se queda mirando, y el resto cae en pausas cortas con cola.
    """
    roll = random.random()
    if roll < 0.18:
        return random.uniform(0.12, 0.38)
    if roll < 0.30:
        return random.uniform(7.0, 14.0)
    return min(6.0, 0.6 + random.expovariate(0.55))


def idle_blink_interval(base: float) -> float:
    """Intervalo entre frames de este parpadeo. `base` es 1/fps del clip.

    Mayor intervalo = parpadeo más lento. La mayoría sale cerca del
    clip; unos pocos son perezosos o rápidos.
    """
    roll = random.random()
    if roll < 0.15:
        scale = random.uniform(1.45, 1.9)
    elif roll < 0.35:
        scale = random.uniform(0.55, 0.8)
    else:
        scale = random.uniform(0.85, 1.2)
    return base * scale


def loop_restart_delay(max_delay: float, idle_eyes: bool) -> float:
    """Pausa al terminar un loop. Los ojos no usan max_delay."""
    if idle_eyes:
        return idle_blink_gap()
    hi = float(max_delay)
    lo = hi / 5.0
    if hi <= lo:
        return hi
    return random.uniform(lo, hi)


class FramebufferWriter:
    """Escribe datos binarios al framebuffer."""
    
    def __init__(self, fb_device: str = "/dev/fb0", simulate: bool = False):
        self.fb_device = fb_device
        self.simulate = simulate
        self._fb = None
        self._consecutive_failures = 0
        self._last_valid_frame: Optional[bytes] = None
        self._write_count = 0
        
        if not simulate:
            self._open_framebuffer()
    
    def _open_framebuffer(self) -> bool:
        """Abre o reabre el dispositivo framebuffer."""
        try:
            if self._fb:
                try:
                    self._fb.close()
                except:
                    pass
            
            self._fb = open(self.fb_device, 'wb')
            logger.info(f"📺 Framebuffer abierto: {self.fb_device}")
            self._consecutive_failures = 0
            return True
        except Exception as e:
            logger.error(f"❌ Error abriendo framebuffer {self.fb_device}: {e}")
            self._fb = None
            return False
    
    def write(self, data: bytes, max_retries: int = 3, skip_black_check: bool = False) -> bool:
        """Escribe datos al framebuffer con reintentos automáticos."""
        if not data:
            logger.error("❌ Intentando escribir datos vacíos al framebuffer")
            return False
        
        # Detectar imagen completamente negra (muestreo distribuido)
        if not skip_black_check:
            # Muestrear en diferentes posiciones de la imagen
            data_len = len(data)
            sample_positions = [0, data_len // 4, data_len // 2, 3 * data_len // 4]
            sample_size = 1000
            non_zero_count = 0
            
            for pos in sample_positions:
                end_pos = min(pos + sample_size, data_len)
                sample = data[pos:end_pos]
                non_zero_count += sum(1 for b in sample if b != 0)
            
            if non_zero_count == 0:
                logger.error(f"❌🖼️  IMAGEN COMPLETAMENTE NEGRA detectada - NO SE ESCRIBIRÁ")
                return False
        
        if self.simulate:
            logger.debug(f"[SIMULADO] Escribiendo {len(data)} bytes al framebuffer")
            self._last_valid_frame = data
            self._write_count += 1
            return True
        
        for attempt in range(max_retries):
            if self._fb is None:
                if not self._open_framebuffer():
                    if attempt < max_retries - 1:
                        time.sleep(0.1)
                    continue
            
            try:
                self._fb.seek(0)
                bytes_written = self._fb.write(data)
                self._fb.flush()
                
                if bytes_written != len(data):
                    logger.error(f"❌ Escritura incompleta: {bytes_written}/{len(data)} bytes")
                    self._consecutive_failures += 1
                    if attempt < max_retries - 1:
                        time.sleep(0.05)
                        continue
                    return False
                
                self._consecutive_failures = 0
                self._last_valid_frame = data
                self._write_count += 1
                return True
                
            except IOError as e:
                self._consecutive_failures += 1
                logger.error(f"❌ Error I/O: {e}")
                
                if self._consecutive_failures >= 3:
                    self._open_framebuffer()
                
                if attempt < max_retries - 1:
                    time.sleep(0.1)
                    continue
                    
            except Exception as e:
                self._consecutive_failures += 1
                logger.error(f"❌ Error inesperado: {e}")
                if attempt < max_retries - 1:
                    time.sleep(0.05)
                    continue
        
        logger.error(f"❌❌❌ FALLO TOTAL después de {max_retries} intentos")
        return False
    
    def close(self):
        """Cierra el framebuffer."""
        if self._fb:
            try:
                self._fb.close()
                logger.info("📺 Framebuffer cerrado")
            except Exception:
                pass
            self._fb = None


class DisplayExecutor:
    """Ejecuta imágenes y animaciones en el framebuffer."""
    
    def __init__(self, fb_device: str = "/dev/fb0", simulate: bool = False,
                 invert: bool = False):
        self.fb_writer = FramebufferWriter(fb_device, simulate)
        self.simulate = simulate
        self.invert = invert
        self.scenes = SceneEngine(invert=invert)
        self.ribbon = FondoRibbon()
        self.neon = VocoderNeon()
        self.spark = SparkHit()
        self.fade = FadeBlack()
        self._want_live = False
        self._scene_resume_at: Optional[float] = None
        self._overlay_gen = 0
        self._resume_gen = 0
        self._pending_live = False
        self._overlay_image: Optional[bytes] = None
        self._idle_over_fondo = False  # idle (ojos o desconectado) sobre el slideshow
        self._anim_source = ""
        self._gesture_done = False
        self.on_gesture_done = None  # un pase de pad terminó: volver al parpadeo
        self._shake = 0.0
        self._shake_t = time.monotonic()
        
        self._render_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._command_queue = queue.Queue(maxsize=100)
        
        self._state_lock = threading.RLock()
        self._current_type: Optional[str] = None
        self._current_image: Optional[bytes] = None
        self._current_animation: Optional[AnimationConfig] = None
        self._animation_frame_idx: int = 0
        self._animation_pack_file = None
        self._mem_frames = None  # frames ya mapeados; si no, se lee el pack
        self._animation_interval: float = 1.0 / 20
        self._blink_base_interval: float = 1.0 / 20
        self._waiting_until: Optional[float] = None
        self._paused = False
        self._last_frame_time: float = 0
        self._frame_accumulator: float = 0

        # Slideshow de fondo: cicla imágenes pre-cargadas mientras dura la canción
        self._slideshow_images: list = []
        self._slideshow_interval: float = FONDO_BASE_INTERVAL
        self._slideshow_base_interval: float = FONDO_BASE_INTERVAL  # interval al BPM canónico de la canción
        self._slideshow_base_bpm: float = 0.0        # BPM de referencia (0 = aún no recibido)
        self._slideshow_loop_beats: Optional[float] = None  # si no None, base_bpm se deriva de loop_beats
        self._slideshow_transition: str = "cut"   # "cut" | "fade"
        self._slideshow_fade_s: float = 0.5
        self._slideshow_start: float = 0.0
        self._slideshow_last_idx: int = 0
        self._slideshow_fade_from: Optional[bytes] = None
        self._slideshow_fade_begin: float = 0.0
        
        self.stats = {
            'images_shown': 0,
            'animations_started': 0,
            'frames_rendered': 0,
            'fb_writes_ok': 0,
            'fb_writes_failed': 0,
        }
        
        self._start_render_thread()
    
    def pause(self):
        """Pausa el display executor (para que status screen tome control)."""
        with self._state_lock:
            self._paused = True
            logger.debug("⏸️  DisplayExecutor pausado")
    
    def resume(self):
        """Resume el display executor."""
        with self._state_lock:
            self._paused = False
            logger.debug("▶️  DisplayExecutor resumido")
    
    def write_raw_frame(self, data: bytes) -> bool:
        """
        Escribe un frame raw directamente al framebuffer.
        Usado por status_screen cuando el display está pausado.
        
        Args:
            data: Bytes del frame (RGB565, 768000 bytes)
            
        Returns:
            True si la escritura fue exitosa
        """
        # Skip black check para frames de status screen (son confiables)
        return self.fb_writer.write(data, skip_black_check=True)
    
    def _start_render_thread(self):
        """Inicia el thread de renderizado."""
        if self._render_thread is not None:
            return
        
        self._stop_event.clear()
        self._render_thread = threading.Thread(
            target=self._render_loop,
            daemon=True,
            name="DisplayRenderer"
        )
        self._render_thread.start()
        logger.debug(f"🎬 Thread de renderizado iniciado ({SYSTEM_FPS} FPS)")
    
    def _close_pack(self):
        self._mem_frames = None
        if self._animation_pack_file:
            try:
                self._animation_pack_file.close()
            except Exception:
                pass
            self._animation_pack_file = None

    def drain_commands(self):
        """Tira comandos aún no procesados (idle/scene/imagen de la canción anterior)."""
        while True:
            try:
                self._command_queue.get_nowait()
            except queue.Empty:
                return

    def show_image(self, data: bytes, cc: int, value: int):
        """Muestra una imagen estática (non-blocking)."""
        try:
            self._command_queue.put_nowait(('image', data, cc, value))
        except:
            self._show_image_internal(data, cc, value)
    
    def _show_image_internal(self, data: bytes, cc: int, value: int):
        """Implementación interna de show_image."""
        with self._state_lock:
            if self._want_live and cc == SPARK_CC and value == SPARK_VALUE:
                # La 01 ya no es el 404: chispazo, y la 01 es el fundido
                # a negro de 8 filas.
                self.spark.trigger()
                self.fade.start(self.scenes.bpm)
                self.stats['images_shown'] += 1
                logger.info(f"✨ Chispazo: CC {cc:03d}/{value:03d}")
                return

            self._close_pack()

            self._current_type = 'image'
            self._current_image = data
            self._current_animation = None
            self._animation_frame_idx = 0
            self._waiting_until = None

            if self._want_live:
                # Plasma sigue renderizando; la foto se mezcla un rato.
                self._overlay_image = data
                self._current_type = 'scene'
                self.scenes.set_scene("live")
                self._arm_live_resume(IMAGE_HOLD_S)
                self.stats['images_shown'] += 1
                logger.info(f"🖼️  Overlay sobre live: CC {cc:03d}/{value:03d}")
                return
            
            write_ok = self.fb_writer.write(data)
            self._overlay_image = None
            if write_ok:
                self.stats['images_shown'] += 1
                self.stats['fb_writes_ok'] += 1
                logger.info(f"🖼️  Imagen mostrada: CC {cc:03d}/{value:03d}")
            else:
                self.stats['fb_writes_failed'] += 1
                logger.error(f"❌ FALLO escribiendo imagen {cc:03d}/{value:03d}")
    
    def play_animation(self, config: AnimationConfig, source: str = "mdcc"):
        """Reproduce una animación (non-blocking).

        `source='idle'` es la animación de espera (ojos/desconectado). Si
        estamos en canción se ignora: si no, un play_animation encolado
        antes del START pinta frames de idle a mitad del tema.
        """
        if source == "idle" and self._want_live:
            return
        try:
            self._command_queue.put_nowait(('animation', config, source))
        except queue.Full:
            self._play_animation_internal(config, source)
    
    def _is_idle_eyes(self, config: Optional[AnimationConfig]) -> bool:
        """El clip de ojos en pausa. En canción el mismo pack no se altera."""
        return (
            config is not None
            and not self._want_live
            and config.loop
            and config.cc == IDLE_EYES_CC
            and config.value == IDLE_EYES_VALUE
        )

    def _play_animation_internal(self, config: AnimationConfig,
                                 source: str = "mdcc"):
        """Implementación interna de play_animation."""
        if source == "idle" and self._want_live:
            return
        animation_id = f"{config.cc:03d}/{config.value:03d}"
        
        with self._state_lock:
            if (self._current_type == 'animation' and 
                self._current_animation and
                self._current_animation.cc == config.cc and
                self._current_animation.value == config.value):
                if source == "gesture":
                    # El mismo gesto otra vez: desde el primer frame.
                    self._animation_frame_idx = 0
                    self._waiting_until = None
                    self._last_frame_time = 0
                    self._frame_accumulator = 0
                    self._gesture_done = False
                    self._anim_source = "gesture"
                    return
                logger.debug(f"⏭️  Animación {animation_id} ya está activa")
                return
            
            self._close_pack()

            mem = config.frame_bytes
            if mem:
                self._mem_frames = mem
            else:
                try:
                    self._animation_pack_file = open(config.pack_path, 'rb')
                except Exception as e:
                    logger.error(f"❌ Error abriendo {config.pack_path}: {e}")
                    return
            
            self._current_type = 'animation'
            self._current_image = None
            self._current_animation = config
            self._animation_frame_idx = 0
            self._waiting_until = None
            self._last_frame_time = 0
            self._frame_accumulator = 0
            fps = config.fps if config.fps and config.fps > 0 else 20
            self._blink_base_interval = 1.0 / fps
            if self._is_idle_eyes(config):
                self._animation_interval = idle_blink_interval(
                    self._blink_base_interval)
            else:
                self._animation_interval = self._blink_base_interval
            # Ojos y desconectado se mezclan si hay slideshow.
            # Sin slideshow (el fondo no cargó) la animación sigue a pantalla llena.
            self._anim_source = source
            self._gesture_done = False
            self._idle_over_fondo = (
                source in ("idle", "gesture") and bool(self._slideshow_images)
            )
            
            self.stats['animations_started'] += 1
            logger.info(
                f"🎬 Animación configurada: {animation_id} "
                f"({len(config.frames)} frames @ {fps} FPS)"
            )

    def set_slideshow(self, images: list, interval: float = 6.0,
                      transition: str = "cut", fade_s: float = 0.5,
                      loop_beats: float = None):
        """Configura el slideshow de fondo para la canción actual.

        Args:
            images: Lista de bytes (RGB565) pre-cargados.
            interval: Segundos por imagen (ignorado si loop_beats está definido y hay BPM).
            transition: "cut" (instantáneo) o "fade" (crossfade).
            fade_s: Duración del crossfade en segundos.
            loop_beats: Duración del loop en beats. Si se recibe BPM, el interval
                        se recalcula automáticamente: interval = (loop_beats/bpm*60) / n_frames.
        """
        with self._state_lock:
            self._slideshow_images = list(images)
            self._slideshow_loop_beats = float(loop_beats) if loop_beats else None
            self._slideshow_interval = max(0.01, float(interval))
            self._slideshow_base_interval = self._slideshow_interval
            self._slideshow_base_bpm = 0.0  # se fija en el primer set_bpm tras set_slideshow
            self._slideshow_transition = transition if transition in ("cut", "fade") else "cut"
            self._slideshow_fade_s = max(0.1, float(fade_s))
            self._slideshow_start = time.monotonic()
            self._slideshow_last_idx = 0
            self._slideshow_fade_from = None
            self.ribbon.reset_tempo_base()
            self._slideshow_fade_begin = 0.0
        logger.info(
            f"🖼️  Slideshow: {len(images)} imágenes, "
            f"intervalo={interval}s, transición={transition}"
        )

    def clear_slideshow(self):
        """Desactiva el slideshow; el plasma vuelve como fondo."""
        with self._state_lock:
            self._slideshow_images = []
            self._slideshow_fade_from = None
            self.ribbon.reset_tempo_base()
        logger.info("🖼️  Slideshow desactivado")

    def set_live(self, on: bool):
        """START/STOP: el plasma es el fondo de la canción. Un MDCC de
        imagen o animación pinta encima y, al terminar, se vuelve aquí."""
        self.drain_commands()
        with self._state_lock:
            self._want_live = on
            self._scene_resume_at = None
            self._pending_live = False
            if on:
                self.scenes.set_scene("live")
                self.ribbon.reset_beat()
                self.neon.clear()
                self.spark.clear()
                self.fade.clear()
                self._current_type = "scene"
                self._close_pack()
                self._current_animation = None
                self._waiting_until = None
                self._overlay_image = None
                self._anim_source = ""
                self._gesture_done = False
            else:
                self.scenes.set_scene(None)
                self.neon.release()
                self.spark.clear()
                self.fade.clear()
                self._overlay_image = None
                self._idle_over_fondo = False
                self._anim_source = ""
                self._gesture_done = False
                self._close_pack()
                self._current_animation = None
                self._waiting_until = None
                if self._current_type in ("scene", "animation"):
                    self._current_type = None

    def _arm_live_resume(self, hold_s: float):
        if not self._want_live:
            return
        self._overlay_gen += 1
        self._resume_gen = self._overlay_gen
        self._scene_resume_at = time.monotonic() + hold_s

    def _resume_live_now(self):
        self._scene_resume_at = None
        self._pending_live = False
        self._overlay_image = None
        if self._want_live:
            self._play_scene_internal("live")

    def play_scene(self, name: str):
        """Activa una escena procedural (non-blocking)."""
        if not self._want_live:
            return
        try:
            self._command_queue.put_nowait(('scene', name))
        except queue.Full:
            self._play_scene_internal(name)

    def _play_scene_internal(self, name: str):
        if not self._want_live:
            return
        with self._state_lock:
            self._close_pack()
            self._current_type = 'scene'
            self._current_image = None
            self._current_animation = None
            self._waiting_until = None
            self._scene_resume_at = None
            self.scenes.set_scene(name)
            logger.info(f"🌌 Escena procedural: {name}")

    def pulse_chord(self, notes, velocity: int = 127):
        """Latigazo del vocoder (ACRD). Solo la raíz pinta; el acorde no."""
        self.neon.pulse(notes, velocity)

    def pulse_hit(self, kind: str, velocity: int = 127):
        """Impulso de bombo/caja/crash. El render lo consume; el GPIO no."""
        self.scenes.pulse(kind, velocity)
        self.ribbon.pulse(kind, velocity)
        if kind == "kick":
            v = max(0.25, min(1.0, velocity / 127.0))
            with self._state_lock:
                self._shake = min(1.0, self._shake + v)

    def _apply_kick_shake(self, frame: bytes, now: float) -> bytes:
        """Temblor del bombo: 2–8 px, más horizontal, ~110 ms de vida."""
        dt = min(0.08, max(0.0, now - self._shake_t))
        self._shake_t = now
        if self._shake <= 1e-3:
            self._shake = 0.0
            return frame
        self._shake *= 0.5 ** (dt / SHAKE_HALF_LIFE_S)
        amp = min(SHAKE_MAX_PX, int(round(self._shake * SHAKE_MAX_PX)))
        if amp <= 0:
            return frame
        dx = random.randint(-amp, amp)
        dy = random.randint(-(amp // 2), amp // 2)
        return shake_rgb565(frame, dx, dy)

    def set_slideshow_bpm(self, bpm: float):
        """Actualiza el intervalo del slideshow en tiempo real (sin delay).
        No toca scenes — solo el fondo."""
        if bpm <= 0:
            return
        ribbon_base = None
        with self._state_lock:
            n = len(self._slideshow_images)
            if n and self._slideshow_base_interval:
                if self._slideshow_loop_beats:
                    base_bpm = self._slideshow_loop_beats * 60 / (self._slideshow_base_interval * n)
                else:
                    if not self._slideshow_base_bpm:
                        self._slideshow_base_bpm = bpm
                        logger.info(f"[FONDO] base_bpm fijado={bpm:.2f} (inmediato)")
                    base_bpm = self._slideshow_base_bpm
                ribbon_base = base_bpm
                ratio = bpm / base_bpm
                new_interval = max(0.01, self._slideshow_base_interval / ratio ** FONDO_BPM_CURVE)
                # El frame se calcula como (now - start) / interval: si solo
                # cambiamos interval se reescala TODO el tiempo transcurrido y
                # el índice salta (carrera mientras se gira el knob, marcha
                # atrás al bajarlo). Re-anclamos start para que la fase actual
                # sea continua y solo cambie la velocidad a partir de ahora.
                now = time.monotonic()
                phase = (now - self._slideshow_start) / self._slideshow_interval
                self._slideshow_start = now - phase * new_interval
                logger.debug(
                    f"[FONDO] bpm={bpm:.2f} base={base_bpm:.2f} ratio={ratio:.4f} "
                    f"interval {self._slideshow_interval:.4f}→{new_interval:.4f}s"
                )
                self._slideshow_interval = new_interval
        self.ribbon.set_bpm(bpm, base=ribbon_base)

    def set_bpm(self, bpm: float):
        """Actualiza scenes al instante audible (sincronizado). No toca el fondo."""
        self.scenes.set_bpm(bpm)
        self.ribbon.set_bpm(bpm)

    @staticmethod
    def _blend_rgb565(plasma: bytes, image: bytes, img_w: float) -> bytes:
        """Mezcla overlay (img_w) sobre el plasma para no congelar BPM/golpes."""
        if len(plasma) != len(image):
            return plasma
        p = np.frombuffer(plasma, dtype="<u2").astype(np.uint16)
        im = np.frombuffer(image, dtype="<u2").astype(np.uint16)
        a = float(img_w)
        ia = 1.0 - a
        pr, pg, pb = (p >> 11) & 31, (p >> 5) & 63, p & 31
        ir, ig, ib = (im >> 11) & 31, (im >> 5) & 63, im & 31
        r = (pr * ia + ir * a).astype(np.uint16)
        g = (pg * ia + ig * a).astype(np.uint16)
        b = (pb * ia + ib * a).astype(np.uint16)
        return ((r << 11) | (g << 5) | b).astype("<u2").tobytes()

    @staticmethod
    def _composite_rgb565(bg: bytes, fg: bytes) -> bytes:
        """Overlay con doble criterio de transparencia:

        1. Píxeles muy oscuros (sum ≤ 6): negro puro y casi-negro, siempre transparentes.
        2. Píxeles azul-dominantes y oscuros (b > r AND sum ≤ 25): tron grid baked
           en los .bin de CC — se muestra el fondo animado a través de ellos.

        Los grises neutros del robot (r ≈ b, sum 7-25) quedan opacos (contenido).
        """
        if len(bg) != len(fg):
            return bg
        bg_arr = np.frombuffer(bg, dtype="<u2")
        fg_arr = np.frombuffer(fg, dtype="<u2")
        fg32 = fg_arr.astype(np.uint32)
        r = (fg32 >> 11) & 0x1F
        g = (fg32 >> 5) & 0x3F
        b = fg32 & 0x1F
        lum = r + g + b
        # Transparente si: muy oscuro (sum ≤ 6) O (azul-dominante Y oscuro ≤ 25)
        transparent = (lum <= 6) | ((b > r) & (lum <= 25))
        return np.where(transparent, bg_arr, fg_arr).astype("<u2").tobytes()

    @staticmethod
    def _composite_sprite(bg: bytes, fg: bytes, ox: int, oy: int,
                          fw: int, fh: int) -> bytes:
        """Mezcla un recorte sobre el fotograma. El negro del recorte no tapa."""
        if len(bg) != WIDTH * HEIGHT * 2 or len(fg) != fw * fh * 2:
            return bg
        bg_arr = np.frombuffer(bg, dtype="<u2").reshape(HEIGHT, WIDTH).copy()
        fg_arr = np.frombuffer(fg, dtype="<u2").reshape(fh, fw)
        x0 = max(0, ox)
        y0 = max(0, oy)
        x1 = min(WIDTH, ox + fw)
        y1 = min(HEIGHT, oy + fh)
        if x1 <= x0 or y1 <= y0:
            return bg
        sx0, sy0 = x0 - ox, y0 - oy
        patch = fg_arr[sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0)]
        pix = patch.astype(np.uint32)
        r = (pix >> 11) & 0x1F
        g = (pix >> 5) & 0x3F
        b = pix & 0x1F
        lum = r + g + b
        transparent = (lum <= 6) | ((b > r) & (lum <= 25))
        region = bg_arr[y0:y1, x0:x1]
        bg_arr[y0:y1, x0:x1] = np.where(transparent, region, patch)
        return bg_arr.astype("<u2").tobytes()

    def _overlay_is_sprite(self, fg: bytes) -> bool:
        cfg = self._current_animation
        if cfg is None:
            return False
        return len(fg) == cfg.width * cfg.height * 2 and (
            cfg.width != WIDTH or cfg.height != HEIGHT
            or cfg.origin_x or cfg.origin_y
        )

    def _get_slideshow_frame(self, now: float) -> Optional[bytes]:
        """Devuelve el frame del slideshow para el instante `now`.

        Llamado desde _write_live_frame() bajo _state_lock. Gestiona
        internamente el estado del fade sin locks adicionales.
        """
        images = self._slideshow_images
        if not images:
            return None
        n = len(images)
        elapsed = now - self._slideshow_start
        idx = int(elapsed / self._slideshow_interval) % n

        if self._slideshow_transition == "cut":
            return images[idx]

        # fade: detectar cambio de imagen y arrancar transición
        if idx != self._slideshow_last_idx:
            self._slideshow_fade_from = images[self._slideshow_last_idx]
            self._slideshow_fade_begin = now
            self._slideshow_last_idx = idx

        if self._slideshow_fade_from is not None:
            fade_elapsed = now - self._slideshow_fade_begin
            if fade_elapsed >= self._slideshow_fade_s:
                self._slideshow_fade_from = None
            else:
                alpha = fade_elapsed / self._slideshow_fade_s
                return self._blend_rgb565(
                    self._slideshow_fade_from, images[idx], alpha)

        return images[idx]

    def _write_live_frame(self):
        now = time.monotonic()
        slideshow = self._get_slideshow_frame(now)
        if slideshow is not None:
            bg = slideshow
        else:
            if self.scenes.name != "live":
                self.scenes.set_scene("live")
            bg = self.scenes.render()
            if not bg:
                return
        # Fondo → cinta → latigazo del vocoder → overlay. La letra tapa
        # los márgenes si los invade; la cinta no pinta donde hay tinta.
        if self._overlay_image:
            if self._overlay_is_sprite(self._overlay_image):
                cfg = self._current_animation
                block = overlay_block_cols(
                    self._overlay_image, ox=cfg.origin_x, oy=cfg.origin_y,
                    fw=cfg.width, fh=cfg.height)
                frame = self.ribbon.blit_rgb565(bg, now, block_cols=block)
                frame = self.neon.blit_rgb565(frame, now)
                frame = self._composite_sprite(
                    frame, self._overlay_image,
                    cfg.origin_x, cfg.origin_y, cfg.width, cfg.height)
            else:
                block = overlay_block_cols(self._overlay_image)
                frame = self.ribbon.blit_rgb565(bg, now, block_cols=block)
                frame = self.neon.blit_rgb565(frame, now)
                frame = self._composite_rgb565(frame, self._overlay_image)
        else:
            frame = self.ribbon.blit_rgb565(bg, now)
            frame = self.neon.blit_rgb565(frame, now)
        frame = self.spark.blit_rgb565(frame, now)
        frame = self.fade.blit_rgb565(frame, now)
        frame = self._apply_kick_shake(frame, now)
        write_ok = self.fb_writer.write(frame, skip_black_check=True)
        if write_ok:
            self.stats['frames_rendered'] += 1
            self.stats['fb_writes_ok'] += 1
        else:
            self.stats['fb_writes_failed'] += 1
    
    def _render_loop(self):
        """Loop principal de renderizado."""
        logger.debug("🎬 Iniciando loop de renderizado")
        
        while not self._stop_event.is_set():
            frame_start = time.monotonic()
            resume_gesture = False
            
            # Si está pausado, solo dormir
            with self._state_lock:
                if self._paused:
                    time.sleep(FRAME_INTERVAL)
                    continue
            
            # Procesar comandos pendientes
            try:
                while True:
                    cmd = self._command_queue.get_nowait()
                    if cmd[0] == 'image':
                        self._show_image_internal(cmd[1], cmd[2], cmd[3])
                    elif cmd[0] == 'animation':
                        source = cmd[2] if len(cmd) > 2 else "mdcc"
                        self._play_animation_internal(cmd[1], source)
                    elif cmd[0] == 'scene':
                        self._play_scene_internal(cmd[1])
            except:
                pass

            if (self._want_live and self._scene_resume_at is not None
                    and time.monotonic() >= self._scene_resume_at
                    and self._resume_gen == self._overlay_gen):
                self._resume_live_now()
            elif self._pending_live:
                self._resume_live_now()
            
            try:
                with self._state_lock:
                    mdcc_anim = (
                        self._current_type == 'animation'
                        and self._current_animation
                        and not self._want_live
                        and not self._idle_over_fondo
                    )
                    live_anim = (
                        self._want_live
                        and self._current_type == 'animation'
                        and self._current_animation
                    )
                    idle_over = (
                        self._idle_over_fondo
                        and self._current_type == 'animation'
                        and self._current_animation
                    )
                    gesture_done = False
                    if live_anim or idle_over or mdcc_anim:
                        if self._anim_source == "gesture-done":
                            pass
                        elif self._waiting_until:
                            if time.monotonic() >= self._waiting_until:
                                self._animation_frame_idx = 0
                                self._waiting_until = None
                                self._last_frame_time = 0
                                self._frame_accumulator = 0
                                if self._is_idle_eyes(self._current_animation):
                                    self._animation_interval = idle_blink_interval(
                                        self._blink_base_interval)
                        else:
                            current_time = time.monotonic()
                            if self._last_frame_time == 0:
                                self._advance_animation()
                                self._last_frame_time = current_time
                                self._frame_accumulator = 0
                            else:
                                dt = current_time - self._last_frame_time
                                # Un salto de reloj hacia atrás no debe
                                # dejar el acumulador en negativo (animación
                                # parada hasta que el reloj lo alcance).
                                if dt < 0:
                                    dt = 0.0
                                self._frame_accumulator += dt
                                self._last_frame_time = current_time
                                if self._frame_accumulator >= self._animation_interval:
                                    self._advance_animation()
                                    self._frame_accumulator -= self._animation_interval
                        gesture_done = self._gesture_done
                        if gesture_done:
                            self._gesture_done = False
                    if (live_anim or idle_over or self._want_live
                            or self._current_type == 'scene'):
                        # Canción o pausa con fondo: slideshow/plasma sigue
                        # y la animación se mezcla encima.
                        self._write_live_frame()
                    elif mdcc_anim and self._current_image is not None:
                        pass  # idle sin slideshow: el frame ya se escribió a pantalla llena
                    resume_gesture = gesture_done and not self._want_live
            
            except Exception as e:
                resume_gesture = False
                logger.error(f"❌ Error en render loop: {e}")

            if resume_gesture and self.on_gesture_done is not None:
                try:
                    self.on_gesture_done()
                except Exception as e:
                    logger.error(f"❌ Error volviendo al idle tras el gesto: {e}")
            
            # Reloj monotónico: al conectar se hace `date -s` para igualar
            # el sinte, y un salto hacia atrás entre las dos lecturas dejaba
            # elapsed negativo y el sleep en semanas (pantalla congelada).
            elapsed = time.monotonic() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(min(sleep_time, FRAME_INTERVAL))
        
        logger.debug("🏁 Loop de renderizado terminado")
    
    def _advance_animation(self):
        """Pasa al siguiente frame del pack.

        En canción (`_want_live`) y en idle con slideshow el frame queda
        como overlay. En idle sin slideshow se escribe a pantalla llena.
        """
        if not self._current_animation:
            return
        if self._mem_frames is None and not self._animation_pack_file:
            return
        
        config = self._current_animation
        
        if self._animation_frame_idx >= len(config.frames):
            if self._anim_source == "gesture":
                # Un pase y se queda el último frame hasta que el
                # orquestador vuelve a poner el parpadeo.
                self._anim_source = "gesture-done"
                self._gesture_done = True
                return
            if self._anim_source == "gesture-done":
                return
            if self._want_live:
                # Durante la canción el clip (loop o no) no se queda dueño
                # de la pantalla: al terminar una pasada vuelve el plasma.
                logger.debug("🏁 Clip de MDCC terminado, vuelve live")
                self._pending_live = True
                return
            # idle overlay (ojos): cae al loop de abajo, el fondo sigue
            if config.loop:
                delay = loop_restart_delay(
                    config.max_delay,
                    self._is_idle_eyes(config),
                )
                self._waiting_until = time.monotonic() + delay
                logger.debug(f"⏸️  Animación completa, esperando {delay:.2f}s")
            else:
                logger.debug(f"🏁 Animación completa (no-loop)")
                self._current_type = None
                self._current_animation = None
                self._close_pack()
            return
        
        frame_info = config.frames[self._animation_frame_idx]
        
        try:
            if self._mem_frames is not None:
                frame_data = self._mem_frames[self._animation_frame_idx]
            else:
                self._animation_pack_file.seek(frame_info['offset'])
                frame_data = self._animation_pack_file.read(frame_info['size'])
            
            if not frame_data:
                logger.error(f"❌ Frame {self._animation_frame_idx} sin datos")
                self.stats['fb_writes_failed'] += 1
                return

            if self._want_live or self._idle_over_fondo:
                self._overlay_image = frame_data
                self._animation_frame_idx += 1
                return

            if self._overlay_is_sprite(frame_data):
                frame_data = self._composite_sprite(
                    b"\x00\x00" * (WIDTH * HEIGHT), frame_data,
                    config.origin_x, config.origin_y,
                    config.width, config.height)
            write_ok = self.fb_writer.write(frame_data)
            
            if write_ok:
                self.stats['frames_rendered'] += 1
                self.stats['fb_writes_ok'] += 1
                logger.debug(f"   Frame {self._animation_frame_idx + 1}/{len(config.frames)}")
            else:
                self.stats['fb_writes_failed'] += 1
            
            self._animation_frame_idx += 1
        
        except Exception as e:
            logger.error(f"❌ Error renderizando frame: {e}")
            self.stats['fb_writes_failed'] += 1
    
    def cleanup(self):
        """Limpieza de recursos."""
        self._stop_event.set()
        
        if self._render_thread and self._render_thread.is_alive():
            self._render_thread.join(timeout=1.0)
        
        with self._state_lock:
            self._close_pack()

        self.fb_writer.close()
        logger.info("🧹 DisplayExecutor limpiado")
    
    def get_stats(self) -> dict:
        """Retorna estadísticas del ejecutor."""
        return self.stats.copy()
