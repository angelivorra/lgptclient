#!/usr/bin/env python3
"""Cache de imágenes y animaciones .bin/pack.bin con prelectura.
Estructura esperada:
  /home/angel/imgs_directo/<CC>/<VAL>/
    - Si existe pack.bin => animación empaquetada y pack.bin.index.json + anim.cfg
    - Si NO existe pack.bin pero existe <VAL>.bin => imagen única.
"""
from __future__ import annotations
import os, json, threading, time
from dataclasses import dataclass
from typing import Dict, List, Optional
import logging

logger = logging.getLogger("cliented.cache")
BASE_DIR = "/home/angel/imgs_directo"

@dataclass
class AnimationFrameIndex:
    offset: int
    size:   int

@dataclass
class AnimationPack:
    width: int
    height: int
    bpp: int
    frames: List[AnimationFrameIndex]
    raw_path: str  # pack.bin path
    fps: int
    loop: bool
    max_delay: float

    @property
    def frame_interval(self) -> float:
        return 1.0 / self.fps if self.fps > 0 else 1/30

class MediaCache:
    def __init__(self, base_dir: str = BASE_DIR):
        self.base_dir = base_dir
        self._image_cache: Dict[str, bytes] = {}
        self._anim_cache: Dict[str, AnimationPack] = {}
        self._lock = threading.RLock()

    def _key(self, cc:int, val:int) -> str:
        return f"{cc:03d}/{val:03d}"

    def get_image(self, cc:int, val:int) -> Optional[bytes]:
        key = self._key(cc,val)
        with self._lock:
            return self._image_cache.get(key)

    def get_animation(self, cc:int, val:int) -> Optional[AnimationPack]:
        key = self._key(cc,val)
        with self._lock:
            return self._anim_cache.get(key)

    def ensure_loaded(self, cc:int, val:int):
        """Carga en memoria la imagen o animación si existe y no está en cache."""
        path_dir = os.path.join(self.base_dir, f"{cc:03d}", f"{val:03d}")
        key = self._key(cc,val)
        with self._lock:
            if key in self._image_cache or key in self._anim_cache:
                return
        if not os.path.isdir(path_dir):
            # Puede ser imagen suelta? /<cc>/<val>.bin
            file_path = os.path.join(self.base_dir, f"{cc:03d}", f"{val:03d}.bin")
            if os.path.isfile(file_path):
                try:
                    data = open(file_path,'rb').read()
                    with self._lock:
                        self._image_cache[key] = data
                    logger.info(f"Imagen cacheada {file_path} ({len(data)} bytes)")
                except Exception as e:
                    logger.error(f"Error leyendo {file_path}: {e}")
            else:
                logger.warning(f"Media no encontrada (ni dir ni archivo): esperado archivo {file_path} o directorio {path_dir}")
            return
        # Directorio: animación o imagen dentro
        pack_path = os.path.join(path_dir, "pack.bin")
        if os.path.isfile(pack_path):
            index_path = pack_path + ".index.json"
            cfg_path = os.path.join(path_dir, "anim.cfg")
            try:
                idx = json.load(open(index_path))
                cfg = json.load(open(cfg_path)) if os.path.isfile(cfg_path) else {"fps":30,"loop":True,"max_delay":2}
                frames = [AnimationFrameIndex(e['offset'], e['size']) for e in idx['entries']]
                anim = AnimationPack(width=idx['width'], height=idx['height'], bpp=idx['bpp'],
                                      frames=frames, raw_path=pack_path,
                                      fps=cfg.get('fps',30), loop=cfg.get('loop',True),
                                      max_delay=cfg.get('max_delay',2))
                with self._lock:
                    self._anim_cache[key] = anim
                logger.info(f"Animación cacheada {pack_path} frames={len(frames)} fps={anim.fps}")
            except Exception as e:
                logger.error(f"Error cargando animación {pack_path}: {e}")
            return
        # Imagen dentro del directorio: <val>.bin
        img_file = os.path.join(path_dir, f"{val:03d}.bin")
        if os.path.isfile(img_file):
            try:
                data = open(img_file,'rb').read()
                with self._lock:
                    self._image_cache[key] = data
                logger.info(f"Imagen cacheada {img_file} ({len(data)} bytes)")
            except Exception as e:
                logger.error(f"Error leyendo {img_file}: {e}")
        else:
            logger.warning(f"Media no encontrada: sin pack.bin y falta archivo {img_file}")

    def preload_batch(self, items: List[tuple[int,int]]):
        for cc,val in items:
            try:
                self.ensure_loaded(cc,val)
            except Exception as e:
                logger.warning(f"Fallo pre-carga {cc}:{val} -> {e}")

    def clear(self):
        with self._lock:
            self._image_cache.clear()
            self._anim_cache.clear()

# Singleton simple
_cache: MediaCache | None = None

def get_cache() -> MediaCache:
    global _cache
    if _cache is None:
        _cache = MediaCache()
    return _cache
