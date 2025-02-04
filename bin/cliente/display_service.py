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
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DisplayService")

class DisplayService:
    def __init__(self, socket_path='/tmp/display.sock'):
        self.socket_path = socket_path
        self.fb = Framebuffer()
        self.current_animation = None
        self.task_queue = asyncio.Queue()
        self.animaciones = list(ANIMACIONES.items())
        
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
        current_timestamp = int(datetime.now().timestamp() * 1000)
        
        logger.info("Procesando mensaje: %s", cleaned_data)
        
        tipo = cleaned_data[0].upper()
        timestamp = int(cleaned_data[1])
        
        data = None
        
        if tipo == "IMG":
            canal = int(cleaned_data[2])
            id_image = int(cleaned_data[3])
            data = {
                'tipo': tipo,
                'id_image': id_image,
                'canal': canal,
                'data': self.get_animation_by_id(id_image)
            }

        if data:
            logger.info("Enviamos evento a display: %s", data)
            await self.task_queue.put((timestamp, data))

    async def task_processor(self):
        while True:
            timestamp, data = await self.task_queue.get()
            current_timestamp = int(datetime.now().timestamp() * 1000)
            
            if timestamp > current_timestamp:
                delay = (timestamp - current_timestamp) / 1000.0
                await asyncio.sleep(delay)
            
            await self.execute_action(data)
            self.task_queue.task_done()

    async def execute_action(self, message):
        # Detener animación actual
        if self.current_animation:
            self.current_animation.cancel()
            self.current_animation = None

        canal = message["canal"]
        logger.info(f"Procesando mensaje: {message}")
        if message["canal"] == 0:
            logger.info(f"Imagen: {message['id_image']}")
            nota = int(message["id_image"])
            if nota == 0:
                self.fb.clear()
            else:
                self.fb.display_image(f"{IMG_DIR}/{nota:03d}.bin")            
        
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
            while True:
                files = sorted(Path(ANIMACIONES_DIR).glob(f"{name}*.bin"))
                if not files:
                    logger.error(f"Animación no encontrada: {name}")
                    return

                for file in files:
                    self.fb.display_image(str(file))
                    await asyncio.sleep(frame_delay)

                if not loop:
                    break
                
                await asyncio.sleep(random.uniform(max_delay/2, max_delay))
                
        except asyncio.CancelledError:
            logger.info("Animación cancelada")
            self.fb.clear()
        except Exception as e:
            logger.error(f"Error en animación: {e}")

    async def start(self):
        self.fb.open()
        server = await asyncio.start_unix_server(
            lambda r, w: self.handle_client(r, w),
            self.socket_path
        )
        logger.info(f"Servidor iniciado en {self.socket_path}")
        
        # Iniciar el procesador de tareas
        asyncio.create_task(self.task_processor())
        
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