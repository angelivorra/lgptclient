import asyncio
import os
import mmap
import getpass
from pathlib import Path

# Framebuffer class for handling the HDMI display
class Framebuffer:
    def __init__(self, fbpath="/dev/fb0"):
        if os.system('getent group video | grep -q "\b'+ getpass.getuser() +'\b"') == 1:
            os.system("sudo adduser " + getpass.getuser() + " video")
        _ = open("/sys/class/graphics/fb0/virtual_size", "r")
        __ = _.read()
        self.screenx, self.screeny = [int(i) for i in __.split(",")]
        _.close()
        _ = open("/sys/class/graphics/fb0/bits_per_pixel", "r")
        self.bpp = int(_.read()[:2])
        _.close()
        self.fbpath = fbpath
        self.fbdev = os.open(self.fbpath, os.O_RDWR)
        self.fb = mmap.mmap(self.fbdev, self.screenx*self.screeny*self.bpp//8, mmap.MAP_SHARED, mmap.PROT_WRITE|mmap.PROT_READ, offset=0)

    def draw_image(self, image):
        self.fb.seek(0)
        self.fb.write(image)

    def clear(self):
        self.fb.seek(0)
        self.fb.write(b'\x00' * (self.screenx * self.screeny * self.bpp // 8))

# Store the task to be cancelled when a new image event arrives
current_task = None

async def handle_image(id: int, loop: int, delay: int):
    global current_task
    if current_task:
        current_task.cancel()
    current_task = asyncio.ensure_future(_display_image_sequence(id, loop, delay))
    await current_task

async def _display_image_sequence(id: int, loop: int, delay: int):
    fb = Framebuffer()
    fb.clear()  # Clear the framebuffer before starting
    
    def load_image(image_id):
        image_path = Path(f"/home/angel/img/{image_id:03d}.xxx")
        if not image_path.exists():
            return None


    if loop <= 0:
        img_data = load_image(id)
        if img_data:
            fb.draw_image(img_data)
    else:
        for i in range(loop):
            img_data = load_image(id + i)
            if img_data:
                fb.draw_image(img_data)
            await asyncio.sleep(delay / 1000)
