#!/usr/bin/env python3
"""Ejecución de imágenes y animaciones según eventos CC.
Si pantalla_flag es False, no escribe en framebuffer pero registra acciones.
"""
from __future__ import annotations
import os, time, json
import threading
import logging
from typing import Optional
try:
    from .media_cache import get_cache, AnimationPack  # ejecución como paquete
    from .framebuffer import get_fb
except ImportError:  # ejecución directa
    import sys, os as _os
    _base = _os.path.dirname(__file__)
    if _base not in sys.path:
        sys.path.append(_base)
    from media_cache import get_cache, AnimationPack  # type: ignore
    from framebuffer import get_fb  # type: ignore

logger = logging.getLogger("cliented.display")

class DisplayManager:
    def __init__(self):
        self._anim_thread: threading.Thread | None = None
        self._anim_stop = threading.Event()
        self._current_key: Optional[str] = None
        self._lock = threading.RLock()
        self.pantalla_enabled = True
        self.anim_start_warn_ms = int(os.environ.get("ANIM_START_WARN_MS", "15"))

    def set_pantalla(self, enabled: bool):
        self.pantalla_enabled = enabled
        logger.info(f"Pantalla enabled={enabled}")

    def stop_animation(self):
        with self._lock:
            if self._anim_thread and self._anim_thread.is_alive():
                self._anim_stop.set()
                self._anim_thread.join(timeout=0.5)
            self._anim_thread = None
            self._anim_stop.clear()
            self._current_key = None

    def handle_cc(self, cc:int, value:int):
        cache = get_cache()
        cache.ensure_loaded(cc, value)
        key = f"{cc:03d}/{value:03d}"
        anim = cache.get_animation(cc,value)
        img = cache.get_image(cc,value)
        if anim:
            self._start_animation(key, anim)
        elif img:
            self.stop_animation()
            self._show_image(img, key)
        else:
            base_cc = os.path.join(cache.base_dir, f"{cc:03d}")
            dir_path = os.path.join(base_cc, f"{value:03d}")
            file_path = os.path.join(base_cc, f"{value:03d}.bin")
            pack_path = os.path.join(dir_path, "pack.bin")
            logger.warning(
                f"No media para CC {cc} val {value} | dir={dir_path} exists_dir={os.path.isdir(dir_path)} pack={pack_path} exists_pack={os.path.isfile(pack_path)} file={file_path} exists_file={os.path.isfile(file_path)}"
            )

    def _show_image(self, data:bytes, key:str):
        if not self.pantalla_enabled:
            #logger.info(f"[SIMULADO] Mostrar imagen {key} ({len(data)} bytes)")
            return
        fb = get_fb()
        fb.blit(data)
        logger.debug(f"Mostrada imagen {key}")

    def _start_animation(self, key:str, anim:AnimationPack):
        # Si ya está esa animación corriendo, nada
        with self._lock:
            if key == self._current_key:
                return
            self.stop_animation()
            self._current_key = key
            self._anim_stop.clear()
            request_ts = time.time()
            t = threading.Thread(target=self._anim_loop, args=(key,anim,request_ts), daemon=True)
            self._anim_thread = t
            t.start()

    def _anim_loop(self, key:str, anim:AnimationPack, request_ts: float):
        logger.debug(f"Inicia animación {key} frames={len(anim.frames)} fps={anim.fps} preload={'YES' if anim.data else 'NO'}")
        start_delay_ms = int((time.time() - request_ts) * 1000)
        if start_delay_ms > self.anim_start_warn_ms:
            logger.warning(f"ANIM_START_LATE key={key} delay={start_delay_ms}ms thr={self.anim_start_warn_ms}ms")
        try:
            frame_interval = anim.frame_interval
            use_data = anim.data is not None
            f = None
            if not use_data:
                f = open(anim.raw_path,'rb')
            last_cycle_start = time.time()
            while not self._anim_stop.is_set():
                for idx, frame in enumerate(anim.frames):
                    if self._anim_stop.is_set():
                        break
                    if use_data:
                        # slice from data
                        try:
                            chunk = anim.data[frame.offset:frame.offset+frame.size]  # type: ignore[index]
                        except Exception:
                            logger.error(f"Slice error frame {idx} off={frame.offset} size={frame.size}")
                            break
                        if self.pantalla_enabled:
                            get_fb().blit(chunk)
                        else:
                            logger.debug(f"[SIM] frame {idx} anim {key}")
                    else:
                        f.seek(frame.offset)
                        data = f.read(frame.size)
                        if self.pantalla_enabled:
                            get_fb().blit(data)
                        else:
                            logger.debug(f"[SIM] frame {idx} anim {key}")
                    # timing
                    elapsed = time.time() - last_cycle_start
                    target = (idx + 1) * frame_interval
                    delay = target - elapsed
                    if delay > 0:
                        self._anim_stop.wait(delay)
                if not anim.loop:
                    break
                last_cycle_start = time.time()
        except Exception as e:
            logger.error(f"Fallo animación {key}: {e}")
        finally:
            if f:
                try: f.close()
                except Exception: pass
            logger.debug(f"Termina animación {key}")
            with self._lock:
                if self._current_key == key:
                    self._current_key = None
                    self._anim_thread = None
                    self._anim_stop.clear()

# Singleton
_display: DisplayManager | None = None

def get_display() -> DisplayManager:
    global _display
    if _display is None:
        _display = DisplayManager()
    return _display
