#!/usr/bin/env python3
"""Acceso simplificado al framebuffer Linux (fb0) para 800x480x16bpp.
Asume formato RGB565 y tamaño fijo (800*480*2 = 768000 bytes).
"""
import os
import mmap
import logging

logger = logging.getLogger("cliented.fb")

FB_PATH = os.environ.get("FRAMEBUFFER", "/dev/fb0")
WIDTH = 800
HEIGHT = 480
BPP = 16
FRAME_SIZE = WIDTH * HEIGHT * (BPP // 8)

class FrameBufferWriter:
    def __init__(self, fb_path: str = FB_PATH):
        self.fb_path = fb_path
        self._fd = None
        self._mmap = None
        self._ensure_open()

    def _ensure_open(self):
        if self._fd is None:
            try:
                self._fd = os.open(self.fb_path, os.O_RDWR)
                self._mmap = mmap.mmap(self._fd, FRAME_SIZE, mmap.MAP_SHARED, mmap.PROT_WRITE | mmap.PROT_READ)
                logger.info(f"Framebuffer abierto {self.fb_path} size={FRAME_SIZE}")
            except Exception as e:
                logger.error(f"No se pudo abrir framebuffer {self.fb_path}: {e}")
                self._fd = None
                self._mmap = None

    def blit(self, data: bytes):
        if not data:
            return
        if len(data) != FRAME_SIZE:
            logger.warning(f"Tamaño bin inesperado ({len(data)}) != FRAME_SIZE {FRAME_SIZE}")
        if self._mmap is None:
            self._ensure_open()
        if self._mmap is None:
            return
        try:
            # Escribir solo lo que tengamos hasta FRAME_SIZE
            view = memoryview(data)[:FRAME_SIZE]
            self._mmap.seek(0)
            self._mmap.write(view)
        except Exception as e:
            logger.error(f"Error escribiendo framebuffer: {e}")

    def close(self):
        try:
            if self._mmap:
                self._mmap.close()
        except Exception:
            pass
        try:
            if self._fd:
                os.close(self._fd)
        except Exception:
            pass
        self._mmap = None
        self._fd = None

_fb_singleton: FrameBufferWriter | None = None

def get_fb() -> FrameBufferWriter:
    global _fb_singleton
    if _fb_singleton is None:
        _fb_singleton = FrameBufferWriter()
    return _fb_singleton
