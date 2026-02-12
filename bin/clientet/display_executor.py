#!/usr/bin/env python3
"""
Ejecutor de display para imágenes y animaciones en framebuffer.

Características:
- Un solo thread para gestionar todo el display (30 FPS)
- Animaciones con loop y delay aleatorio entre repeticiones
- Cambio instantáneo entre imágenes y animaciones
"""
import os
import time
import random
import logging
import threading
import queue
from typing import Optional
from pathlib import Path

from media_manager import AnimationConfig

logger = logging.getLogger("clientet.display")

# Constantes
SYSTEM_FPS = 30  # FPS del thread de renderizado
ANIMATION_FPS = 20  # FPS para todas las animaciones
FRAME_INTERVAL = 1.0 / SYSTEM_FPS  # ~0.033 segundos
ANIMATION_FRAME_INTERVAL = 1.0 / ANIMATION_FPS  # 0.05 segundos


class FramebufferWriter:
    """Escribe datos binarios al framebuffer."""
    
    def __init__(self, fb_device: str = "/dev/fb0", simulate: bool = False):
        """
        Args:
            fb_device: Path al dispositivo framebuffer
            simulate: Si True, simula escritura sin acceso real al hardware
        """
        self.fb_device = fb_device
        self.simulate = simulate
        self._fb = None
        self._consecutive_failures = 0
        self._last_valid_frame: Optional[bytes] = None  # Cache del último frame válido
        self._write_count = 0
        self._retry_count = 0
        self._reopen_count = 0
        
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
    
    def write(self, data: bytes, max_retries: int = 3) -> bool:
        """
        Escribe datos al framebuffer con reintentos automáticos.
        
        Args:
            data: Datos binarios de la imagen
            max_retries: Número máximo de reintentos
            
        Returns:
            True si la escritura fue exitosa, False en caso contrario
        """
        # Verificar datos antes de escribir
        if not data:
            logger.error("❌ Intentando escribir datos vacíos al framebuffer")
            return False
        
        expected_size = 768000  # 640x400x3 bytes
        if len(data) != expected_size:
            logger.warning(f"⚠️  Tamaño de datos incorrecto: {len(data)} bytes (esperado: {expected_size})")
        
        # 🔍 DETECTAR IMAGEN COMPLETAMENTE NEGRA
        sample_size = min(10000, len(data))
        sample = data[:sample_size]
        non_zero_count = sum(1 for b in sample if b != 0)
        
        if non_zero_count == 0:
            logger.error(
                f"❌🖼️  IMAGEN COMPLETAMENTE NEGRA detectada! "
                f"(muestreados {sample_size} bytes, todos=0) - NO SE ESCRIBIRÁ"
            )
            return False
        
        # Info de contenido (solo cada 50 escrituras para no saturar log)
        self._write_count += 1
        if self._write_count % 50 == 0:
            avg_brightness = sum(sample) / len(sample)
            logger.debug(
                f"🔍 Muestra de imagen: {non_zero_count}/{sample_size} bytes no-cero, "
                f"brillo promedio: {avg_brightness:.1f}/255"
            )
        
        if self.simulate:
            logger.debug(f"[SIMULADO] Escribiendo {len(data)} bytes al framebuffer")
            self._last_valid_frame = data
            return True
        
        # INTENTAR ESCRIBIR CON REINTENTOS
        for attempt in range(max_retries):
            if self._fb is None:
                logger.warning(f"⚠️  Framebuffer cerrado, intentando reabrir... (intento {attempt + 1}/{max_retries})")
                if not self._open_framebuffer():
                    if attempt < max_retries - 1:
                        time.sleep(0.1)  # Esperar 100ms antes de reintentar
                    continue
            
            try:
                self._fb.seek(0)
                bytes_written = self._fb.write(data)
                self._fb.flush()
                
                if bytes_written != len(data):
                    logger.error(f"❌ Escritura incompleta: {bytes_written}/{len(data)} bytes (intento {attempt + 1})")
                    self._consecutive_failures += 1
                    
                    if attempt < max_retries - 1:
                        self._retry_count += 1
                        logger.warning(f"🔄 Reintentando escritura... ({attempt + 2}/{max_retries})")
                        time.sleep(0.05)  # 50ms entre reintentos
                        continue
                    return False
                
                # ÉXITO!
                if attempt > 0:
                    logger.info(f"✅ Escritura exitosa después de {attempt + 1} intento(s)")
                
                self._consecutive_failures = 0
                self._last_valid_frame = data
                return True
                
            except IOError as e:
                self._consecutive_failures += 1
                logger.error(
                    f"❌ Error de I/O escribiendo al framebuffer (intento {attempt + 1}/{max_retries}): {e} "
                    f"- ¿Vibraciones/cables sueltos?"
                )
                
                # Si hay muchos fallos consecutivos, intentar reabrir el framebuffer
                if self._consecutive_failures >= 3:
                    logger.warning(
                        f"⚠️  {self._consecutive_failures} fallos consecutivos - "
                        f"intentando reabrir framebuffer..."
                    )
                    self._reopen_count += 1
                    if self._open_framebuffer():
                        logger.info("✅ Framebuffer reabierto exitosamente")
                
                if attempt < max_retries - 1:
                    self._retry_count += 1
                    time.sleep(0.1)  # Esperar más tiempo en errores I/O
                    continue
                    
            except Exception as e:
                self._consecutive_failures += 1
                logger.error(f"❌ Error inesperado escribiendo al framebuffer (intento {attempt + 1}): {e}")
                
                if attempt < max_retries - 1:
                    self._retry_count += 1
                    time.sleep(0.05)
                    continue
        
        # Todos los intentos fallaron
        logger.error(f"❌❌❌ FALLO TOTAL después de {max_retries} intentos - PANTALLA PROBABLEMENTE EN NEGRO")
        return False
    
    def rewrite_last_frame(self) -> bool:
        """Reescribe el último frame válido (para recuperación)."""
        if self._last_valid_frame:
            logger.info("🔄 Reescribiendo último frame válido...")
            return self.write(self._last_valid_frame, max_retries=5)
        return False
    
    def get_stats(self) -> dict:
        """Retorna estadísticas del framebuffer writer."""
        return {
            'writes': self._write_count,
            'retries': self._retry_count,
            'reopens': self._reopen_count,
            'consecutive_failures': self._consecutive_failures,
        }
    
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
    """
    Ejecuta imágenes y animaciones en el framebuffer con un único thread a 30 FPS.
    
    - Un solo thread a 30 FPS constante
    - Animaciones reproducidas a 20 FPS
    - Cambio instantáneo entre contenidos
    - Loop con delay aleatorio para animaciones
    """
    
    def __init__(self, fb_device: str = "/dev/fb0", simulate: bool = False):
        """
        Args:
            fb_device: Path al dispositivo framebuffer
            simulate: Si True, simula display sin hardware real
        """
        self.fb_writer = FramebufferWriter(fb_device, simulate)
        
        # Thread único de renderizado
        self._render_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Cola de comandos para evitar contención del lock
        self._command_queue = queue.Queue(maxsize=100)
        
        # Estado actual (protegido por lock)
        self._state_lock = threading.Lock()
        self._current_type: Optional[str] = None  # 'image' o 'animation'
        self._current_image: Optional[bytes] = None
        self._current_animation: Optional[AnimationConfig] = None
        self._animation_frame_idx: int = 0
        self._animation_pack_file = None
        self._waiting_until: Optional[float] = None  # Para delays entre loops
        
        # Control de velocidad de animación (20 FPS)
        self._last_frame_time: float = 0
        self._frame_accumulator: float = 0
        
        # Estadísticas y diagnósticos
        self.stats = {
            'images_shown': 0,
            'animations_started': 0,
            'frames_rendered': 0,
            'fb_writes_ok': 0,
            'fb_writes_failed': 0,
            'blank_screen_detected': 0,
            'black_images_rejected': 0,
            'long_gaps_detected': 0,
        }
        self._last_fb_write_time = 0
        self._last_content_description = "None"
        
        # Thread de watchdog para detectar gaps largos
        self._watchdog_thread: Optional[threading.Thread] = None
        self._watchdog_running = False
        
        # Iniciar thread de renderizado
        self._start_render_thread()
        
        # Iniciar watchdog
        self._start_watchdog()
    
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
        logger.debug(f"🎬 Thread de renderizado iniciado ({SYSTEM_FPS} FPS sistema, {ANIMATION_FPS} FPS animaciones)")
    
    def _start_watchdog(self):
        """¡Inicia el thread watchdog para detectar gaps largos sin escritura."""
        if self._watchdog_thread is not None:
            return
        
        self._watchdog_running = True
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop,
            daemon=True,
            name="DisplayWatchdog"
        )
        self._watchdog_thread.start()
        logger.debug("🐕 Watchdog de display iniciado (alerta cada 2s sin actividad)")
    
    def _watchdog_loop(self):
        """Loop del watchdog que monitorea gaps largos sin escritura al framebuffer."""
        GAP_THRESHOLD = 2.0  # Segundos sin actividad antes de alertar
        CHECK_INTERVAL = 0.5  # Verificar cada 0.5s
        
        while self._watchdog_running:
            time.sleep(CHECK_INTERVAL)
            
            if self._last_fb_write_time == 0:
                continue  # Aún no se ha escrito nada
            
            current_time = time.time()
            gap = current_time - self._last_fb_write_time
            
            if gap > GAP_THRESHOLD:
                with self._state_lock:
                    content_type = self._current_type
                    has_content = (content_type == 'image' and self._current_image) or \
                                  (content_type == 'animation' and self._current_animation)
                
                if has_content:
                    # Hay contenido activo pero no se ha escrito en mucho tiempo
                    self.stats['long_gaps_detected'] += 1
                    logger.warning(
                        f"⚠️🐕 GAP LARGO DETECTADO: {gap:.1f}s sin escribir al framebuffer! "
                        f"Tipo actual: {content_type}, último: {self._last_content_description} "
                        f"- ¿PANTALLA EN NEGRO?"
                    )
                    # Resetear para evitar spam (alertará de nuevo si continúa)
                    self._last_fb_write_time = current_time
    
    def show_image(self, data: bytes, cc: int, value: int):
        """
        Muestra una imagen estática (non-blocking).
        
        Args:
            data: Datos binarios de la imagen
            cc: Control change (para logging)
            value: Valor (para logging)
        """
        try:
            # Usar cola para evitar bloquear el scheduler
            self._command_queue.put_nowait(('image', data, cc, value))
        except:
            # Si la cola está llena, ejecutar directamente (fallback)
            self._show_image_internal(data, cc, value)
    
    def _show_image_internal(self, data: bytes, cc: int, value: int):
        """Implementación interna de show_image."""
        with self._state_lock:
            # Cerrar archivo de animación si existe
            if self._animation_pack_file:
                try:
                    self._animation_pack_file.close()
                except Exception:
                    pass
                self._animation_pack_file = None
            
            # Cambiar a modo imagen
            self._current_type = 'image'
            self._current_image = data
            self._current_animation = None
            self._animation_frame_idx = 0
            self._waiting_until = None
            
            # Escribir imagen al framebuffer inmediatamente
            write_ok = self.fb_writer.write(data)
            
            if write_ok:
                self.stats['images_shown'] += 1
                self.stats['fb_writes_ok'] += 1
                self._last_fb_write_time = time.time()
                self._last_content_description = f"Imagen {cc:03d}/{value:03d}"
                logger.info(f"🖼️  Imagen mostrada: CC {cc:03d}/{value:03d} ({len(data)} bytes)")
            else:
                self.stats['fb_writes_failed'] += 1
                # Verificar si fue rechazada por ser negra
                if data:
                    sample = data[:1000]
                    if all(b == 0 for b in sample):
                        self.stats['black_images_rejected'] += 1
                        logger.error(
                            f"❌🖼️  Imagen {cc:03d}/{value:03d} RECHAZADA: completamente negra! "
                            f"- Archivo corrupto o problema al cargar"
                        )
                logger.error(f"❌ FALLO escribiendo imagen {cc:03d}/{value:03d} - ¡PANTALLA PUEDE ESTAR EN BLANCO!")
    
    def play_animation(self, config: AnimationConfig):
        """
        Reproduce una animación (non-blocking).
        
        Args:
            config: Configuración de la animación a reproducir
        """
        try:
            # Usar cola para evitar bloquear el scheduler
            self._command_queue.put_nowait(('animation', config))
        except:
            # Si la cola está llena, ejecutar directamente (fallback)
            self._play_animation_internal(config)
    
    def _play_animation_internal(self, config: AnimationConfig):
        """Implementación interna de play_animation."""
        animation_id = f"{config.cc:03d}/{config.value:03d}"
        
        with self._state_lock:
            # Si ya está reproduciendo esta animación, no hacer nada
            if (self._current_type == 'animation' and 
                self._current_animation and
                self._current_animation.cc == config.cc and
                self._current_animation.value == config.value):
                logger.debug(f"⏭️  Animación {animation_id} ya está activa")
                return
            
            # Cerrar archivo anterior si existe
            if self._animation_pack_file:
                try:
                    self._animation_pack_file.close()
                except Exception:
                    pass
                self._animation_pack_file = None
            
            # Abrir nuevo archivo pack.bin
            try:
                self._animation_pack_file = open(config.pack_path, 'rb')
            except Exception as e:
                logger.error(f"❌ Error abriendo {config.pack_path}: {e}")
                return
            
            # Cambiar a modo animación
            self._current_type = 'animation'
            self._current_image = None
            self._current_animation = config
            self._animation_frame_idx = 0
            self._waiting_until = None
            self._last_frame_time = 0  # Resetear control de tiempo
            self._frame_accumulator = 0
            
            self.stats['animations_started'] += 1
            logger.info(
                f"🎬 Animación configurada: {animation_id} "
                f"({len(config.frames)} frames @ {ANIMATION_FPS} FPS, loop={config.loop}, "
                f"max_delay={config.max_delay}s)"
            )
    
    def _render_loop(self):
        """
        Loop principal de renderizado a 30 FPS del sistema.
        Las animaciones se reproducen a 20 FPS.
        Se ejecuta en un thread separado.
        """
        logger.debug("🎬 Iniciando loop de renderizado")
        
        while not self._stop_event.is_set():
            frame_start = time.time()
            
            # Procesar comandos pendientes en la cola (sin bloquear)
            try:
                while True:
                    cmd = self._command_queue.get_nowait()
                    if cmd[0] == 'image':
                        self._show_image_internal(cmd[1], cmd[2], cmd[3])
                    elif cmd[0] == 'animation':
                        self._play_animation_internal(cmd[1])
            except:
                pass  # Cola vacía
            
            try:
                # Detectar si no hay contenido activo (pantalla en blanco)
                with self._state_lock:
                    if self._current_type is None:
                        # No hay contenido activo - pantalla debería estar en blanco
                        time_since_last_write = time.time() - self._last_fb_write_time
                        if time_since_last_write > 5.0:  # Más de 5 segundos sin contenido
                            self.stats['blank_screen_detected'] += 1
                            logger.warning(
                                f"⚠️  PANTALLA SIN CONTENIDO por {time_since_last_write:.1f}s "
                                f"(último: {self._last_content_description})"
                            )
                            self._last_fb_write_time = time.time()  # Evitar spam
                    
                    if self._current_type == 'image' and self._current_image:
                        # Renderizar imagen estática (solo una vez hasta que cambie)
                        # No hacemos nada, la imagen ya se mostró
                        pass
                    
                    elif self._current_type == 'animation' and self._current_animation:
                        # ¿Estamos esperando el delay entre loops?
                        if self._waiting_until:
                            if time.time() >= self._waiting_until:
                                # Termina el delay, reiniciar animación
                                self._animation_frame_idx = 0
                                self._waiting_until = None
                                self._last_frame_time = 0
                                self._frame_accumulator = 0
                                logger.debug(f"🔄 Reiniciando loop de animación")
                            else:
                                # Seguimos esperando, no renderizar nada
                                pass
                        else:
                            # Controlar velocidad de animación (20 FPS)
                            current_time = time.time()
                            
                            if self._last_frame_time == 0:
                                # Primera vez, renderizar inmediatamente
                                self._render_animation_frame()
                                self._last_frame_time = current_time
                                self._frame_accumulator = 0
                            else:
                                # Acumular tiempo transcurrido
                                self._frame_accumulator += (current_time - self._last_frame_time)
                                self._last_frame_time = current_time
                                
                                # ¿Es momento de avanzar al siguiente frame? (20 FPS = 0.05s por frame)
                                if self._frame_accumulator >= ANIMATION_FRAME_INTERVAL:
                                    self._render_animation_frame()
                                    self._frame_accumulator -= ANIMATION_FRAME_INTERVAL
            
            except Exception as e:
                logger.error(f"❌ Error en render loop: {e}")
            
            # Dormir hasta el próximo frame (30 FPS del sistema)
            elapsed = time.time() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
        
        logger.debug("🏁 Loop de renderizado terminado")
    
    def _render_animation_frame(self):
        """
        Renderiza el frame actual de la animación (debe llamarse con lock).
        """
        if not self._current_animation or not self._animation_pack_file:
            return
        
        config = self._current_animation
        
        # ¿Ya terminamos todos los frames?
        if self._animation_frame_idx >= len(config.frames):
            if config.loop:
                # Calcular delay aleatorio entre max_delay/5 y max_delay
                min_delay = config.max_delay / 5.0
                max_delay = config.max_delay
                delay = random.uniform(min_delay, max_delay)
                
                self._waiting_until = time.time() + delay
                logger.debug(
                    f"⏸️  Animación completa, esperando {delay:.2f}s antes de repetir "
                    f"(entre {min_delay:.1f}s y {max_delay:.1f}s)"
                )
            else:
                # No es loop, detener animación
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
        
        # Leer y renderizar frame
        frame_info = config.frames[self._animation_frame_idx]
        
        try:
            self._animation_pack_file.seek(frame_info['offset'])
            frame_data = self._animation_pack_file.read(frame_info['size'])
            
            if not frame_data:
                logger.error(f"❌ Frame {self._animation_frame_idx} sin datos - archivo corrupto?")
                self.stats['fb_writes_failed'] += 1
                return
            
            write_ok = self.fb_writer.write(frame_data)
            
            if write_ok:
                self.stats['frames_rendered'] += 1
                self.stats['fb_writes_ok'] += 1
                self._last_fb_write_time = time.time()
                self._last_content_description = f"Anim {config.cc:03d}/{config.value:03d} frame {self._animation_frame_idx + 1}"
                
                logger.debug(
                    f"   Frame {self._animation_frame_idx + 1}/{len(config.frames)}"
                )
            else:
                self.stats['fb_writes_failed'] += 1
                logger.error(f"❌ FALLO escribiendo frame {self._animation_frame_idx + 1} - ¡PANTALLA POSIBLEMENTE EN BLANCO!")
            
            # Avanzar al siguiente frame
            self._animation_frame_idx += 1
        
        except IOError as e:
            logger.error(f"❌ Error I/O leyendo frame {self._animation_frame_idx}: {e} (archivo corrupto/movido?)")
            self.stats['fb_writes_failed'] += 1
        except Exception as e:
            logger.error(f"❌ Error renderizando frame {self._animation_frame_idx}: {e}")
            self.stats['fb_writes_failed'] += 1
    
    def cleanup(self):
        """Limpieza de recursos."""
        # Parar watchdog
        self._watchdog_running = False
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            self._watchdog_thread.join(timeout=1.0)
        
        # Parar thread de renderizado
        self._stop_event.set()
        
        if self._render_thread and self._render_thread.is_alive():
            self._render_thread.join(timeout=1.0)
        
        # Cerrar archivo de animación si existe
        with self._state_lock:
            if self._animation_pack_file:
                try:
                    self._animation_pack_file.close()
                except Exception:
                    pass
                self._animation_pack_file = None
        
        # Cerrar framebuffer
        self.fb_writer.close()
        logger.info("🧹 DisplayExecutor limpiado")
    
    def get_stats(self) -> dict:
        """Retorna estadísticas del ejecutor."""
        return self.stats.copy()
    
    def print_stats(self):
        """Imprime estadísticas de forma legible."""
        total_writes = self.stats['fb_writes_ok'] + self.stats['fb_writes_failed']
        success_rate = (self.stats['fb_writes_ok'] / total_writes * 100) if total_writes > 0 else 0
        
        logger.info("\n" + "="*60)
        logger.info("📊 Estadísticas del DisplayExecutor")
        logger.info("="*60)
        logger.info(f"Imágenes mostradas:      {self.stats['images_shown']}")
        logger.info(f"Animaciones iniciadas:   {self.stats['animations_started']}")
        logger.info(f"Frames renderizados:     {self.stats['frames_rendered']}")
        logger.info(f"")
        
        # Estadísticas del framebuffer writer
        fb_stats = self.fb_writer.get_stats()
        logger.info(f"Framebuffer:")
        logger.info(f"  Escrituras totales:    {fb_stats['writes']}")
        logger.info(f"  Reintentos necesarios: {fb_stats['retries']}")
        logger.info(f"  Reaperturas FB:        {fb_stats['reopens']}")
        logger.info(f"  Fallos consecutivos:   {fb_stats['consecutive_failures']}")
        logger.info(f"")
        logger.info(f"Escrituras framebuffer:  {total_writes} total")
        logger.info(f"  ✅ Exitosas:           {self.stats['fb_writes_ok']} ({success_rate:.1f}%)")
        logger.info(f"  ❌ Fallidas:           {self.stats['fb_writes_failed']}")
        logger.info(f"  🖼️  Imágenes negras:     {self.stats['black_images_rejected']}")
        logger.info(f"  ⚠️  Pantalla en blanco: {self.stats['blank_screen_detected']} veces")
        logger.info(f"  🐕 Gaps largos:        {self.stats['long_gaps_detected']} veces")
        logger.info(f"")
        logger.info(f"Último contenido:        {self._last_content_description}")
        logger.info("="*60)
        
        if self.stats['fb_writes_failed'] > 0:
            logger.warning(
                f"⚠️  Se detectaron {self.stats['fb_writes_failed']} fallos de escritura. "
                f"Posibles causas: cables sueltos, framebuffer ocupado, hardware defectuoso"
            )


if __name__ == '__main__':
    # Test del DisplayExecutor
    import asyncio
    from media_manager import MediaManager
    
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s.%(msecs)03d %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    async def test_display():
        # Inicializar
        base_path = "/home/angel/images"
        media = MediaManager(base_path)
        display = DisplayExecutor(simulate=True)
        
        logger.info("\n" + "="*60)
        logger.info("Test del DisplayExecutor")
        logger.info("="*60)
        
        try:
            # Test 1: Mostrar imagen
            logger.info("\n--- Test 1: Mostrar imagen estática ---")
            img = media.get_image(2, 3)
            if img:
                display.show_image(img, 2, 3)
            
            await asyncio.sleep(1)
            
            # Test 2: Reproducir animación
            logger.info("\n--- Test 2: Reproducir animación ---")
            anim = media.get_animation(3, 1)
            if anim:
                display.play_animation(anim)
                await asyncio.sleep(3)  # Dejar reproducir 3 segundos
            
            # Test 3: Cambiar a otra animación (debe parar la anterior)
            logger.info("\n--- Test 3: Cambiar animación ---")
            anim2 = media.get_animation(3, 2)
            if anim2:
                display.play_animation(anim2)
                await asyncio.sleep(2)
            
            # Test 4: Parar animación con imagen
            logger.info("\n--- Test 4: Parar animación con imagen ---")
            img2 = media.get_image(2, 9)
            if img2:
                display.show_image(img2, 2, 9)
            
            await asyncio.sleep(1)
            
            # Mostrar estadísticas
            display.print_stats()
            media.print_stats()
            
        finally:
            display.cleanup()
        
        logger.info("\n✅ Test completado")
    
    asyncio.run(test_display())
