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
from scenes import SceneEngine

logger = logging.getLogger("cliente.display")

SYSTEM_FPS = 30
FRAME_INTERVAL = 1.0 / SYSTEM_FPS
# Imagen estática durante una canción: se ve un rato y vuelve al plasma.
IMAGE_HOLD_S = 2.0


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
        self._want_live = False
        self._scene_resume_at: Optional[float] = None
        self._overlay_gen = 0
        self._resume_gen = 0
        self._pending_live = False
        self._overlay_image: Optional[bytes] = None
        
        self._render_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._command_queue = queue.Queue(maxsize=100)
        
        self._state_lock = threading.RLock()
        self._current_type: Optional[str] = None
        self._current_image: Optional[bytes] = None
        self._current_animation: Optional[AnimationConfig] = None
        self._animation_frame_idx: int = 0
        self._animation_pack_file = None
        self._animation_interval: float = 1.0 / 20
        self._waiting_until: Optional[float] = None
        self._paused = False
        self._last_frame_time: float = 0
        self._frame_accumulator: float = 0
        
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
            if self._animation_pack_file:
                try:
                    self._animation_pack_file.close()
                except Exception:
                    pass
                self._animation_pack_file = None
            
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
                logger.debug(f"⏭️  Animación {animation_id} ya está activa")
                return
            
            self._close_pack()
            
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
            self._animation_interval = 1.0 / fps
            
            self.stats['animations_started'] += 1
            logger.info(
                f"🎬 Animación configurada: {animation_id} "
                f"({len(config.frames)} frames @ {fps} FPS)"
            )

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
                self._current_type = "scene"
                self._close_pack()
                self._current_animation = None
                self._waiting_until = None
                self._overlay_image = None
            else:
                self.scenes.set_scene(None)
                self._overlay_image = None
                if self._current_type == "scene":
                    self._current_type = None

    def _arm_live_resume(self, hold_s: float):
        if not self._want_live:
            return
        self._overlay_gen += 1
        self._resume_gen = self._overlay_gen
        self._scene_resume_at = time.time() + hold_s

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

    def pulse_hit(self, kind: str, velocity: int = 127):
        """Impulso de bombo/caja/crash. El render lo consume; el GPIO no."""
        self.scenes.pulse(kind, velocity)

    def set_bpm(self, bpm: float):
        self.scenes.set_bpm(bpm)

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

    def _write_live_frame(self):
        if self.scenes.name != "live":
            self.scenes.set_scene("live")
        frame = self.scenes.render()
        if not frame:
            return
        if self._overlay_image:
            frame = self._blend_rgb565(frame, self._overlay_image, 0.5)
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
            frame_start = time.time()
            
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
                    and time.time() >= self._scene_resume_at
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
                    )
                    live_anim = (
                        self._want_live
                        and self._current_type == 'animation'
                        and self._current_animation
                    )
                    if live_anim or (mdcc_anim):
                        if self._waiting_until:
                            if time.time() >= self._waiting_until:
                                self._animation_frame_idx = 0
                                self._waiting_until = None
                                self._last_frame_time = 0
                                self._frame_accumulator = 0
                        else:
                            current_time = time.time()
                            if self._last_frame_time == 0:
                                self._render_animation_frame()
                                self._last_frame_time = current_time
                                self._frame_accumulator = 0
                            else:
                                self._frame_accumulator += (
                                    current_time - self._last_frame_time)
                                self._last_frame_time = current_time
                                if self._frame_accumulator >= self._animation_interval:
                                    self._render_animation_frame()
                                    self._frame_accumulator -= self._animation_interval
                    elif self._want_live:
                        self._write_live_frame()
                    elif self._current_type == 'scene':
                        self._write_live_frame()
            
            except Exception as e:
                logger.error(f"❌ Error en render loop: {e}")
            
            elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
        
        logger.debug("🏁 Loop de renderizado terminado")
    
    def _render_animation_frame(self):
        """Renderiza el frame actual de la animación."""
        if not self._current_animation or not self._animation_pack_file:
            return
        
        config = self._current_animation
        
        if self._animation_frame_idx >= len(config.frames):
            if self._want_live:
                # Durante la canción el clip (loop o no) no se queda dueño
                # de la pantalla: al terminar una pasada vuelve el plasma.
                logger.debug("🏁 Clip de MDCC terminado, vuelve live")
                self._pending_live = True
                return
            if config.loop:
                min_delay = config.max_delay / 5.0
                max_delay = config.max_delay
                delay = random.uniform(min_delay, max_delay)
                
                self._waiting_until = time.time() + delay
                logger.debug(f"⏸️  Animación completa, esperando {delay:.2f}s")
            else:
                logger.debug(f"🏁 Animación completa (no-loop)")
                self._current_type = None
                self._current_animation = None
                if self._animation_pack_file:
                    try:
                        self._animation_pack_file.close()
                    except Exception:
                        pass
                    self._animation_pack_file = None
            return
        
        frame_info = config.frames[self._animation_frame_idx]
        
        try:
            self._animation_pack_file.seek(frame_info['offset'])
            frame_data = self._animation_pack_file.read(frame_info['size'])
            
            if not frame_data:
                logger.error(f"❌ Frame {self._animation_frame_idx} sin datos")
                self.stats['fb_writes_failed'] += 1
                return
            
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
            if self._animation_pack_file:
                try:
                    self._animation_pack_file.close()
                except Exception:
                    pass
                self._animation_pack_file = None
        
        self.fb_writer.close()
        logger.info("🧹 DisplayExecutor limpiado")
    
    def get_stats(self) -> dict:
        """Retorna estadísticas del ejecutor."""
        return self.stats.copy()
