import asyncio
import os
import mmap
import getpass
from pathlib import Path
import random

# Framebuffer class for handling the HDMI display
class Framebuffer:
    def __init__(self, fbpath="/dev/fb0"):
        if os.system('getent group video | grep -q "\b'+ getpass.getuser() +'\b"') == 1:
            os.system("sudo adduser " + getpass.getuser() + " video")
        # _ = open("/sys/class/graphics/fb0/virtual_size", "r")
        # __ = _.read()
        # self.screenx, self.screeny = [int(i) for i in __.split(",")]
        # _.close()
        # _ = open("/sys/class/graphics/fb0/bits_per_pixel", "r")
        # self.bpp = int(_.read()[:2])
        # print(f"Screenx {self.screenx} ScreenY {self.screeny} bpp {self.bpp}")
        # _.close()
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

# Store the task to be cancelled when a new image event arrives
current_task = None

async def activate_image(id: int, velocity: int):
    if velocity == 127:
        velocity = 0
    #print(f"activate_image({id},{velocity})")
    await handle_image(id,velocity, 50)
    

async def handle_image(id: int, loop: int, delay: int):
    global current_task
    if current_task:
        #print(f"cancel()")
        current_task.cancel()
    #print(f"activate_image({id},{loop},{delay})")
    current_task = asyncio.ensure_future(_display_image_sequence(id+1, loop, delay))
    await current_task

async def _display_image_sequence(id: int, loop: int, delay: int):
    fb = Framebuffer()
    fb.clear()  # Clear the framebuffer before starting
    print(f"ImageSequence({id:03d},{loop})")
    
    def load_image(image_id):
        print(f"/home/angel/images/{image_id:03d}.bin")
        image_path = Path(f"/home/angel/images/{image_id:03d}.bin")
    
        if not image_path.exists():
            return None
        
        # Open the binary image file and read its contents
        with open(image_path, "rb") as f:
            img_data = f.read()
        
        return img_data


    if loop <= 0:
        img_data = load_image(id)
        if img_data:
            fb.draw_image(img_data)
    else:
        while True:            
            for i in range(loop):
                img_data = load_image(id + i)
                if img_data:
                    fb.draw_image(img_data)
                await asyncio.sleep(delay / 1000)
            r1 = random.randint(1, 4)
            await asyncio.sleep(r1)
            
            
