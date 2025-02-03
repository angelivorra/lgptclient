from datetime import datetime
import glob
import logging
import asyncio
import signal
import os
import random

logger = logging.getLogger(__name__)


class DisplayManager:
    def __init__(self, fb):
        self.fb = fb
        self.current_state = "off"
        self.animation_task = None

    async def show_animation(self, name, fps=30, loop=True, max_delay=2.0):
        frame_delay = 1.0 / fps
        while True:
            pattern = f"/home/angel/animaciones/{name}*.bin"
            files = sorted(glob.glob(pattern))
                
            if not files:
                return
            
            for file in files:
                self.fb.display_image(file)
                await asyncio.sleep(frame_delay)
            if not loop:
                break
            #calculate delay, minimo max_delay/2, maximo max_delay
            delay = random.uniform(max_delay / 2, max_delay)
            await asyncio.sleep(delay)  # Espera entre animaciones
            
    async def show_image(self, image_id, scheduled_timestamp):
        if self.animation_task:
            logger.debug("Cancelling current animation task")
            self.animation_task.cancel()
            try:
                await self.animation_task
            except asyncio.CancelledError:
                pass

        image_path = f"/home/angel/images/{image_id:03d}.bin"
        if os.path.exists(image_path):   
            now = datetime.now().timestamp() * 1000
            wait_ms = max(0, scheduled_timestamp - now)
            if wait_ms > 0:
                await asyncio.sleep(wait_ms / 1000)

            self.fb.display_image(image_path)
        else:
            logger.error(f"Image file not found: {image_path}")

    async def set_state(self, state, image_id=None):
        if self.animation_task:
            logger.debug("Cancelling current animation task")
            self.animation_task.cancel()
            try:
                await self.animation_task
            except asyncio.CancelledError:
                pass

        self.current_state = state
        if state == "connecting":
            self.animation_task = asyncio.create_task(self.show_animation("connect"))
        elif state == "connected":
            self.animation_task = asyncio.create_task(self.show_animation("eyes", 20, max_delay=5.0))
        elif state == "image":
            if image_id:
                image_path = f"/home/angel/images/{image_id:03d}.bin"
                self.fb.display_image(image_path)
        elif state == "off":
            self.fb.display_image("/home/angel/images/001.bin")

async def shutdown(loop, signal=None):
    if signal:
        logger.info(f"Received exit signal {signal.name}...")
    
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    logger.info(f"Canceling {len(tasks)} outstanding tasks")
    
    for task in tasks:
        task.cancel()
    
    await asyncio.sleep(1)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Task raised an exception: {result}")
    
    logger.info("Tasks canceled, stopping loop")
    loop.stop()

def setup_signal_handlers(loop):
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(loop, sig)))