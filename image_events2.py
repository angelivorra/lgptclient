import asyncio
import os
import mmap
import getpass
from pathlib import Path
import random
import glob
from typing import Optional
from contextlib import suppress


class ImageHandler:
    def __init__(self, fbpath="/dev/fb0"):
        self._current_task: Optional[asyncio.Task] = None
        self._is_running: bool = True
        if os.system('getent group video | grep -q "\b'+ getpass.getuser() +'\b"') == 1:
            os.system("sudo adduser " + getpass.getuser() + " video")
        self.screenx = 800
        self.screeny = 480
        self.bpp = 16
        self.fbpath = fbpath
        self.fbdev = os.open(self.fbpath, os.O_RDWR)
        self.fb = mmap.mmap(self.fbdev, self.screenx*self.screeny*self.bpp//8, mmap.MAP_SHARED, mmap.PROT_WRITE|mmap.PROT_READ, offset=0)

    def draw_image(self, image):
        self.fb.seek(0)
        self.fb.write(image)

    def clear(self):
        self.fb.seek(0)
        self.fb.write(b'\x00' * (self.screenx * self.screeny * self.bpp // 8))

    async def activate_image(self, id: int, velocity: int) -> None:
        """Activate an image with the given id and velocity."""
        normalized_velocity = 0 if velocity == 127 else velocity
        await self.handle_image(id, normalized_velocity, 50)

    async def handle_image(self, id: int, loop: int, delay: int) -> None:
        """Handle image display with proper task management."""
        await self._cancel_current_task()
        
        self._current_task = asyncio.create_task(
            self._display_image_loop(id, loop, delay)
        )
        
        try:
            await self._current_task
        except asyncio.CancelledError:
            with suppress(asyncio.CancelledError):
                await self._current_task

    async def _cancel_current_task(self) -> None:
        """Safely cancel the current task if it exists."""
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._current_task

    async def _display_image_loop(self, id: int, loop: int, delay: int) -> None:
        """Core image display loop."""
        try:
            while self._is_running:
                img_data = self.load_image(id)
                if img_data:
                    self.draw_image(img_data)
                await asyncio.sleep(delay / 1000)
                
                if loop > 0:
                    for i in range(loop):
                        img_data = self.load_image(id + i)
                        if img_data:
                            self.draw_image(img_data)
                        await asyncio.sleep(delay / 1000)
                    r1 = random.randint(1, 4)
                    await asyncio.sleep(r1)
                if loop <= 0:
                    break
                
        except asyncio.CancelledError:
            raise

    async def play_animation(self, name: str, fps: int, max_delay: float) -> None:
        """Play animation from files matching name pattern at specified fps."""
        await self._cancel_current_task()
        
        self._current_task = asyncio.create_task(
            self._animation_loop(name, fps, max_delay)
        )
        
        try:
            await self._current_task
        except asyncio.CancelledError:
            with suppress(asyncio.CancelledError):
                await self._current_task

    async def _animation_loop(self, name: str, fps: int, max_delay: float) -> None:
        """Core animation loop logic."""
        try:
            while self._is_running:
                # Get all matching files sorted
                pattern = f"/home/angel/animaciones/{name}*.bin"
                files = sorted(glob.glob(pattern))
                
                if not files:
                    return
                
                # Calculate frame delay from fps
                frame_delay = 1.0 / fps
                
                # Play animation frames
                for file in files:
                    with open(file, 'rb') as f:
                        self.draw_image(f.read())
                    await asyncio.sleep(frame_delay)
                
                # Wait random time between max_delay/2 and max_delay
                delay = random.uniform(max_delay/2, max_delay)
                await asyncio.sleep(delay)
                
        except asyncio.CancelledError:
            raise

    async def cleanup(self) -> None:
        """Cleanup method for proper shutdown."""
        self._is_running = False
        await self._cancel_current_task()

# Create global instance
image_handler = ImageHandler()

# Main interface functions
async def activate_image(id: int, velocity: int) -> None:
    await image_handler.activate_image(id, velocity)

async def handle_image(id: int, loop: int, delay: int) -> None:
    await image_handler.handle_image(id, loop, delay)

async def play_animation(name: str, fps: int, max_delay: float) -> None:
    await image_handler.play_animation(name, fps, max_delay)