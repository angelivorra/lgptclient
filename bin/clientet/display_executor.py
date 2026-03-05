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
        
        if not simulate:
            try:
                self._fb = open(fb_device, 'wb')
                logger.info(f"📺 Framebuffer abierto: {fb_device}")
            except Exception as e:
                logger.error(f"❌ Error abriendo framebuffer {fb_device}: {e}")
                logger.info("🔄 Cambiando a modo simulación")
                self.simulate = True
    
    def write(self, data: bytes):
        """
        Escribe datos al framebuffer.
        
        Args:
            data: Datos binarios de la imagen (debe ser del tamaño correcto)
        """
        if self.simulate:
            logger.debug(f"[SIMULADO] Escribiendo {len(data)} bytes al framebuffer")
            return
        
        if self._fb is None:
            logger.warning("⚠️  Framebuffer no está abierto")
            return
        
        try:
            self._fb.seek(0)
            self._fb.write(data)
            self._fb.flush()
        except Exception as e:
            logger.error(f"❌ Error escribiendo al framebuffer: {e}")
    
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
        
        # Estadísticas
        self.stats = {
            'images_shown': 0,
            'animations_started': 0,
            'frames_rendered': 0,
        }
        
        # Iniciar thread de renderizado
        self._start_render_thread()
    
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
            self.fb_writer.write(data)
            
            self.stats['images_shown'] += 1
            logger.info(f"🖼️  Imagen mostrada: CC {cc:03d}/{value:03d} ({len(data)} bytes)")
    
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
                with self._state_lock:
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
            
            self.fb_writer.write(frame_data)
            self.stats['frames_rendered'] += 1
            
            logger.debug(
                f"   Frame {self._animation_frame_idx + 1}/{len(config.frames)}"
            )
            
            # Avanzar al siguiente frame
            self._animation_frame_idx += 1
        
        except Exception as e:
            logger.error(f"❌ Error renderizando frame {self._animation_frame_idx}: {e}")
    
    def cleanup(self):
        """Limpieza de recursos."""
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
        logger.info("\n" + "="*60)
        logger.info("📊 Estadísticas del DisplayExecutor")
        logger.info("="*60)
        logger.info(f"Imágenes mostradas:      {self.stats['images_shown']}")
        logger.info(f"Animaciones iniciadas:   {self.stats['animations_started']}")
        logger.info(f"Frames renderizados:     {self.stats['frames_rendered']}")
        logger.info("="*60)


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
