class FramebufferService:
    def __init__(self, fbpath="/dev/fb0"):
        self.fbpath = fbpath
        self.screenx = 800
        self.screeny = 480
        self.bpp = 16
        self.fbdev = self._open_framebuffer()
        self.fb = self._map_framebuffer()

    def _open_framebuffer(self):
        return os.open(self.fbpath, os.O_RDWR)

    def _map_framebuffer(self):
        return mmap.mmap(self.fbdev, self.screenx * self.screeny * self.bpp // 8, 
                         mmap.MAP_SHARED, mmap.PROT_WRITE | mmap.PROT_READ, offset=0)

    def draw_image(self, image):
        self.fb.seek(0)
        self.fb.write(image)

    def clear(self):
        self.fb.seek(0)
        self.fb.write(b'\x00' * (self.screenx * self.screeny * self.bpp // 8))