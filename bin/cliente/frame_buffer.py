import logging
import mmap
import os
from typing import Union

logger = logging.getLogger(__name__)

class Framebuffer:
    def __init__(self, device='/dev/fb0'):
        logger.debug("Initializing framebuffer")
        self.device = device
        self.width = 800  # Ajusta según la resolución de tu pantalla
        self.height = 480
        self.bpp = 16  # Bytes por pixel (32 bits)
        self.screen_size = self.width * self.height * self.bpp // 8
        self.fb = None
        self.mapped_fb = None
        logger.debug("Framebuffer initialized")

    def open(self):
        logger.debug("Opening framebuffer")
        self.fb = os.open(self.device, os.O_RDWR)
        self.mapped_fb = mmap.mmap(self.fb, self.screen_size, mmap.MAP_SHARED, mmap.PROT_WRITE)

    def close(self):
        logger.debug("Closing framebuffer")
        if self.mapped_fb:
            self.mapped_fb.close()
        if self.fb:
            os.close(self.fb)
        logger.debug("Framebuffer closed")

    def display_image(self, image_path):
        logger.debug(f"Displaying image: {image_path}")
        with open(image_path, 'rb') as f:
            image_data = f.read()
        self.mapped_fb.seek(0)
        self.mapped_fb.write(image_data)
    
    def blit(self, frame_bytes: Union[bytes, bytearray, memoryview]):
        """Escribe directamente un frame ya cargado en el framebuffer.

        Evita reabrir el archivo cuando los datos ya están en caché.
        """
        if len(frame_bytes) != self.screen_size:
            logger.warning(
                f"Frame size mismatch: expected {self.screen_size} got {len(frame_bytes)}"
            )
        self.mapped_fb.seek(0)
        # memoryview hace la escritura sin copiar si es posible
        if not isinstance(frame_bytes, (bytes, bytearray)):
            frame_bytes = memoryview(frame_bytes)
        self.mapped_fb.write(frame_bytes)
        
    def clear(self):
        logger.debug("Clearing framebuffer")
        self.mapped_fb.seek(0)
        self.mapped_fb.write(b'\x00' * self.screen_size)