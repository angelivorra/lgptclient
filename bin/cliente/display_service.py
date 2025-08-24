from datetime import datetime
import os
import json
import asyncio
import logging
import random
import glob
import time
from pathlib import Path
from frame_buffer import Framebuffer
from typing import Dict, List

ANIMACIONES_DIR = "/home/angel/animaciones"
IMG_DIR = "/home/angel/images"

ANIMACIONES = {
    "connect": {
        "fps": 30,
        "loop": True,
        "max_delay": 2.0
    },
    "eyes": {
        "fps": 30,
        "loop": True,
        "max_delay": 5.0
    },
    "off": {
        "fps": 30,
        "loop": False,
        "max_delay": 2.0
    },
    "tres": {
        "fps": 30,
        "loop": True,
        "max_delay": 0.2
    },
    "dos": {
        "fps": 30,
        "loop": True,
        "max_delay": 0.2
    },
    "uno": {
        "fps": 30,
        "loop": True,
        "max_delay": 0.2
    },
    "zero": {
        "fps": 30,
        "loop": True,
        "max_delay": 0.2
    }
}

# Configuración básica de logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("DisplayService")

class DisplayService:
    def __init__(self, socket_path='/tmp/display.sock'):
        self.socket_path = socket_path
        self.fb = Framebuffer()
        self.current_animation = None
        self.task_queue = asyncio.Queue()
        self.animaciones = list(ANIMACIONES.items())
        # Caches
        self._frame_list_cache = {}  # nombre_anim -> lista de paths
        self._frame_bytes_cache = {}  # path -> bytes frame
        # Buffer reutilizable para lecturas (usado solo al cargar por primera vez)
        self._read_buffer = bytearray(self.fb.screen_size)

        # Asegurar que el socket no existe previamente
        try:
            os.unlink(self.socket_path)
        except OSError:
            if os.path.exists(self.socket_path):
                raise

    def get_animation_by_id(self, animation_id):
        if 0 <= animation_id < len(self.animaciones):
            return self.animaciones[animation_id]
        return None

    async def handle_client(self, reader, _):
        try:
            while True:
                data = await reader.read(1024)
                if not data:
                    break
                try:
                    message = data.decode()
                    await self.process_message(message)
                except Exception as e:
                    logger.error(f"Error procesando mensaje: {e}")

        except ConnectionResetError:
            logger.warning("Conexión reseteada por el cliente")
        finally:
            logger.info("Cliente desconectado")

    async def process_message(self, message):
        cleaned_data = message.split(',')
        
        logger.info("Procesando mensaje: %s", cleaned_data)
        
        tipo = cleaned_data[0].upper()
        timestamp = int(cleaned_data[1])
        
        data = None
        
        if tipo == "IMG":
            canal = int(cleaned_data[2])
            id_image = int(cleaned_data[3])
            await self.execute_action({
                'tipo': tipo,
                'id_image': id_image,
                'canal': canal,
                'data': self.get_animation_by_id(id_image)
            })
            

    async def execute_action(self, message):
        # Detener animación actual
        if self.current_animation:
            logger.info(f"Hay una animacion. Intentamos detener")
            self.current_animation.cancel()
            self.current_animation = None
            await asyncio.sleep(0.1)
            logger.info(f"Animacion detenida")

        canal = message["canal"]        
        if message["canal"] == 0:
            logger.info(f"Imagen: {message['id_image']}")
            nota = int(message["id_image"])
            if nota == 0:
                self.fb.clear()
            else:
                logger.info(f"Mostramos imagen: {nota}")
                path = f"{IMG_DIR}/{nota:03d}.bin"
                frame_bytes = self._get_frame_bytes(path)
                if frame_bytes:
                    self.fb.blit(frame_bytes)
                else:
                    logger.error(f"No se pudo cargar imagen {path}")            
        
        if message["canal"] == 1:
            logger.info(f"Animación: {message['data'][0]}")
            self.current_animation = asyncio.create_task(
                self.show_animation(
                    name=message['data'][0],
                    fps=message['data'][1]['fps'],
                    loop=message['data'][1]['loop'],
                    max_delay=message['data'][1]['max_delay']
                )
            )

    async def show_animation(self, name, fps=30, loop=True, max_delay=2.0):
        try:
            frame_delay = 1.0 / fps
            logger.info(f"Comenzamos animacion: {name}")
            files = self._get_animation_file_list(name)
            if not files:
                logger.error(f"Animación no encontrada: {name}")
                return
            # Precarga de bytes (lazy: se cargan al primer uso)
            while True:
                start_cycle = time.monotonic()
                for file_path in files:
                    frame_bytes = self._get_frame_bytes(file_path)
                    if not frame_bytes:
                        logger.error(f"Fallo cargando frame {file_path}")
                        continue
                    self.fb.blit(frame_bytes)
                    await asyncio.sleep(frame_delay)
                if not loop:
                    break
                jitter = random.uniform(max_delay/2, max_delay)
                # Ajuste para que el ciclo completo (frames + espera) se mantenga estable
                elapsed = time.monotonic() - start_cycle
                restante = jitter - elapsed + len(files)*frame_delay
                if restante > 0:
                    await asyncio.sleep(restante)
                
        except asyncio.CancelledError:
            logger.info("Animación cancelada")
            self.fb.clear()
        except Exception as e:
            logger.error(f"Error en animación: {e}")

    # ---------------------------
    # Métodos de caché
    # ---------------------------
    def _get_animation_file_list(self, name: str) -> List[str]:
        lst = self._frame_list_cache.get(name)
        if lst is None:
            pattern = f"{name}*.bin"
            lst = [str(p) for p in sorted(Path(ANIMACIONES_DIR).glob(pattern))]
            self._frame_list_cache[name] = lst
        return lst

    def _get_frame_bytes(self, path: str) -> bytes:
        data = self._frame_bytes_cache.get(path)
        if data is not None:
            return data
        # Cargar desde disco usando buffer reutilizable
        try:
            size = os.path.getsize(path)
            if size != self.fb.screen_size:
                logger.warning(
                    f"Tamaño inesperado en {path}: {size} != {self.fb.screen_size}"
                )
            with open(path, 'rb') as f:
                mv = memoryview(self._read_buffer)
                read_total = 0
                while read_total < size:
                    n = f.readinto(mv[read_total:])
                    if n == 0:
                        break
                    read_total += n
                data = bytes(mv[:read_total])
            self._frame_bytes_cache[path] = data
            return data
        except Exception as e:
            logger.error(f"Error cargando frame {path}: {e}")
            return b''

    async def start(self):
        self.fb.open()
        server = await asyncio.start_unix_server(
            lambda r, w: self.handle_client(r, w),
            self.socket_path
        )
        logger.info(f"Servidor iniciado en {self.socket_path}")
       
        # Iniciar animación por defecto "eyes"

        anim_config = ANIMACIONES["eyes"]
        self.current_animation = asyncio.create_task(
            self.show_animation(
                name="eyes",
                fps=anim_config["fps"],
                loop=anim_config["loop"],
                max_delay=anim_config["max_delay"]
            )
        )
       
        async with server:
            await server.serve_forever()

    def stop(self):
        if self.current_animation:
            self.current_animation.cancel()
        self.fb.close()

if __name__ == "__main__":
    service = DisplayService()
    try:
        asyncio.run(service.start())
    except KeyboardInterrupt:
        service.stop()
        logger.info("Servicio detenido")