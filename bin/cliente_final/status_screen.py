#!/usr/bin/env python3
"""
Generador de pantalla de estado con cara de robot.

Genera una imagen RGB565 de 800x480 mostrando:
- Cara de robot estilizada
- IP actual
- Estado de conexión con servidor TCP
- Uso de disco duro

Se actualiza cada segundo.
"""
import socket
import shutil
import struct
import logging
import threading
import time
from typing import Optional, Callable

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logging.warning("PIL no disponible - pantalla de estado no funcionará")

logger = logging.getLogger("cliente.status")

# Configuración de pantalla
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 480
FRAME_SIZE = SCREEN_WIDTH * SCREEN_HEIGHT * 2  # RGB565 = 2 bytes por pixel

# Colores (RGB)
COLOR_BG = (0, 0, 0)           # Negro
COLOR_ROBOT = (0, 200, 255)    # Cyan claro
COLOR_EYES = (0, 255, 100)     # Verde brillante
COLOR_TEXT = (200, 200, 200)   # Gris claro
COLOR_OK = (0, 255, 0)         # Verde
COLOR_ERROR = (255, 50, 50)    # Rojo
COLOR_WARNING = (255, 200, 0)  # Amarillo


def rgb_to_rgb565(r: int, g: int, b: int) -> int:
    """Convierte RGB888 a RGB565."""
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def image_to_rgb565(img: Image.Image) -> bytes:
    """Convierte una imagen PIL a bytes RGB565 (little endian)."""
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    # Intentar usar numpy para conversión rápida
    try:
        import numpy as np
        
        # Convertir a array numpy
        arr = np.array(img, dtype=np.uint16)
        
        # Extraer canales
        r = arr[:, :, 0]
        g = arr[:, :, 1]
        b = arr[:, :, 2]
        
        # Convertir a RGB565
        rgb565 = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
        
        # Convertir a bytes (little endian)
        return rgb565.astype('<u2').tobytes()
        
    except ImportError:
        # Fallback a implementación Python pura (más lenta)
        pixels = list(img.getdata())
        data = bytearray(len(pixels) * 2)
        
        for i, (r, g, b) in enumerate(pixels):
            rgb565 = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
            # Little endian
            data[i * 2] = rgb565 & 0xFF
            data[i * 2 + 1] = (rgb565 >> 8) & 0xFF
        
        return bytes(data)


class StatusScreen:
    """Genera pantallas de estado con cara de robot."""
    
    def __init__(self, invertir: bool = False):
        self.connected = False
        self.server_host = ""
        self.server_port = 0
        self.invertir = invertir  # Invertir imagen 180°
        self._font = None
        self._font_small = None
        self._font_large = None
        self._load_fonts()
        
        # Estado de la interfaz
        self._blink_state = True
        self._frame_count = 0
    
    def _load_fonts(self):
        """Carga fuentes para renderizado."""
        if not PIL_AVAILABLE:
            return
        
        # Intentar cargar fuentes del sistema
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        ]
        
        for path in font_paths:
            try:
                self._font = ImageFont.truetype(path, 24)
                self._font_small = ImageFont.truetype(path, 18)
                self._font_large = ImageFont.truetype(path, 36)
                logger.debug(f"Fuente cargada: {path}")
                return
            except (IOError, OSError):
                continue
        
        # Fallback a fuente por defecto
        logger.warning("No se encontraron fuentes TrueType, usando fuente por defecto")
        self._font = ImageFont.load_default()
        self._font_small = self._font
        self._font_large = self._font
    
    def set_connection_status(self, connected: bool, host: str = "", port: int = 0):
        """Actualiza el estado de conexión."""
        self.connected = connected
        self.server_host = host
        self.server_port = port
    
    def _get_local_ip(self) -> str:
        """Obtiene la IP local."""
        try:
            # Crear socket UDP para obtener IP local
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            try:
                return socket.gethostbyname(socket.gethostname())
            except Exception:
                return "Sin IP"
    
    def _get_disk_usage(self) -> tuple:
        """Obtiene uso de disco."""
        try:
            usage = shutil.disk_usage("/")
            total_gb = usage.total / (1024**3)
            used_gb = usage.used / (1024**3)
            free_gb = usage.free / (1024**3)
            percent = (usage.used / usage.total) * 100
            return used_gb, total_gb, percent
        except Exception:
            return 0, 0, 0
    
    def _draw_robot_face(self, draw: ImageDraw.ImageDraw, x: int, y: int, width: int, height: int):
        """Dibuja la cara del robot."""
        # Cabeza (rectángulo redondeado)
        head_margin = 20
        head_rect = [x + head_margin, y + head_margin, 
                     x + width - head_margin, y + height - head_margin]
        
        # Borde de la cabeza
        for i in range(3):
            offset = i
            draw.rectangle(
                [head_rect[0] + offset, head_rect[1] + offset,
                 head_rect[2] - offset, head_rect[3] - offset],
                outline=COLOR_ROBOT,
                width=2
            )
        
        # Ojos
        eye_width = 60
        eye_height = 40
        eye_y = y + 80
        left_eye_x = x + width // 2 - 80
        right_eye_x = x + width // 2 + 20
        
        # Color de ojos según estado de conexión
        eye_color = COLOR_OK if self.connected else COLOR_ERROR
        
        # Parpadeo
        if self._blink_state or self._frame_count % 30 < 25:
            # Ojo izquierdo
            draw.rectangle(
                [left_eye_x, eye_y, left_eye_x + eye_width, eye_y + eye_height],
                fill=eye_color,
                outline=COLOR_ROBOT
            )
            # Ojo derecho
            draw.rectangle(
                [right_eye_x, eye_y, right_eye_x + eye_width, eye_y + eye_height],
                fill=eye_color,
                outline=COLOR_ROBOT
            )
        else:
            # Ojos cerrados (línea)
            draw.line(
                [left_eye_x, eye_y + eye_height // 2, 
                 left_eye_x + eye_width, eye_y + eye_height // 2],
                fill=eye_color, width=4
            )
            draw.line(
                [right_eye_x, eye_y + eye_height // 2,
                 right_eye_x + eye_width, eye_y + eye_height // 2],
                fill=eye_color, width=4
            )
        
        # Boca (expresión según estado)
        mouth_y = y + 160
        mouth_width = 120
        mouth_x = x + width // 2 - mouth_width // 2
        
        if self.connected:
            # Sonrisa
            draw.arc(
                [mouth_x, mouth_y - 20, mouth_x + mouth_width, mouth_y + 40],
                start=0, end=180,
                fill=COLOR_OK, width=4
            )
        else:
            # Triste
            draw.arc(
                [mouth_x, mouth_y + 20, mouth_x + mouth_width, mouth_y + 60],
                start=180, end=360,
                fill=COLOR_ERROR, width=4
            )
        
        # Antenas
        antenna_base_y = y + head_margin
        antenna_height = 30
        # Antena izquierda
        draw.line(
            [x + width // 2 - 40, antenna_base_y, 
             x + width // 2 - 50, antenna_base_y - antenna_height],
            fill=COLOR_ROBOT, width=3
        )
        draw.ellipse(
            [x + width // 2 - 58, antenna_base_y - antenna_height - 8,
             x + width // 2 - 42, antenna_base_y - antenna_height + 8],
            fill=COLOR_ROBOT
        )
        # Antena derecha
        draw.line(
            [x + width // 2 + 40, antenna_base_y,
             x + width // 2 + 50, antenna_base_y - antenna_height],
            fill=COLOR_ROBOT, width=3
        )
        draw.ellipse(
            [x + width // 2 + 42, antenna_base_y - antenna_height - 8,
             x + width // 2 + 58, antenna_base_y - antenna_height + 8],
            fill=COLOR_ROBOT
        )
    
    def generate_frame(self) -> bytes:
        """
        Genera un frame de la pantalla de estado.
        
        Returns:
            Bytes en formato RGB565 (768000 bytes)
        """
        if not PIL_AVAILABLE:
            logger.error("PIL no disponible - retornando frame vacío")
            return bytes(FRAME_SIZE)
        
        self._frame_count += 1
        
        # Crear imagen
        img = Image.new('RGB', (SCREEN_WIDTH, SCREEN_HEIGHT), COLOR_BG)
        draw = ImageDraw.Draw(img)
        
        # Borde exterior para verificar que se dibuja algo
        draw.rectangle([0, 0, SCREEN_WIDTH-1, SCREEN_HEIGHT-1], outline=COLOR_ROBOT, width=3)
        
        # Sección izquierda: Cara de robot (300x250)
        robot_x = 30
        robot_y = 40
        robot_width = 280
        robot_height = 230
        self._draw_robot_face(draw, robot_x, robot_y, robot_width, robot_height)
        
        # Línea divisoria
        div_x = 340
        draw.line(
            [div_x, 30, div_x, SCREEN_HEIGHT - 30],
            fill=COLOR_ROBOT, width=2
        )
        
        # Sección derecha: Información
        info_x = 380
        info_y = 50
        line_height = 60
        
        # Título
        title = "ESTADO DEL SISTEMA"
        draw.text((info_x, info_y), title, fill=COLOR_ROBOT, font=self._font_large)
        
        # Separador
        info_y += 50
        draw.line([info_x, info_y, SCREEN_WIDTH - 40, info_y], fill=COLOR_ROBOT, width=1)
        info_y += 20
        
        # IP Local
        ip = self._get_local_ip()
        draw.text((info_x, info_y), "IP LOCAL:", fill=COLOR_TEXT, font=self._font_small)
        info_y += 25
        draw.text((info_x + 20, info_y), ip, fill=COLOR_OK, font=self._font)
        info_y += line_height
        
        # Estado de conexión TCP
        draw.text((info_x, info_y), "SERVIDOR TCP:", fill=COLOR_TEXT, font=self._font_small)
        info_y += 25
        if self.connected:
            status_text = f"CONECTADO"
            status_color = COLOR_OK
            draw.text((info_x + 20, info_y), status_text, fill=status_color, font=self._font)
            info_y += 28
            server_text = f"{self.server_host}:{self.server_port}"
            draw.text((info_x + 20, info_y), server_text, fill=COLOR_TEXT, font=self._font_small)
        else:
            status_text = "DESCONECTADO"
            status_color = COLOR_ERROR
            draw.text((info_x + 20, info_y), status_text, fill=status_color, font=self._font)
        info_y += line_height
        
        # Uso de disco
        used_gb, total_gb, percent = self._get_disk_usage()
        draw.text((info_x, info_y), "DISCO:", fill=COLOR_TEXT, font=self._font_small)
        info_y += 25
        
        # Barra de progreso
        bar_width = 300
        bar_height = 25
        bar_x = info_x + 20
        bar_y = info_y
        
        # Fondo de la barra
        draw.rectangle(
            [bar_x, bar_y, bar_x + bar_width, bar_y + bar_height],
            outline=COLOR_ROBOT, width=2
        )
        
        # Relleno de la barra
        fill_width = int(bar_width * percent / 100)
        if percent < 70:
            bar_color = COLOR_OK
        elif percent < 90:
            bar_color = COLOR_WARNING
        else:
            bar_color = COLOR_ERROR
        
        if fill_width > 0:
            draw.rectangle(
                [bar_x + 2, bar_y + 2, bar_x + fill_width - 2, bar_y + bar_height - 2],
                fill=bar_color
            )
        
        info_y += bar_height + 10
        disk_text = f"{used_gb:.1f} GB / {total_gb:.1f} GB ({percent:.1f}%)"
        draw.text((info_x + 20, info_y), disk_text, fill=COLOR_TEXT, font=self._font_small)
        
        # Hora actual
        info_y = SCREEN_HEIGHT - 60
        current_time = time.strftime("%H:%M:%S")
        current_date = time.strftime("%d/%m/%Y")
        draw.text((info_x, info_y), f"{current_date}  {current_time}", fill=COLOR_ROBOT, font=self._font)
        
        # Indicador de actividad (punto parpadeante)
        if self._frame_count % 2 == 0:
            draw.ellipse(
                [SCREEN_WIDTH - 50, SCREEN_HEIGHT - 50, SCREEN_WIDTH - 30, SCREEN_HEIGHT - 30],
                fill=COLOR_OK if self.connected else COLOR_ERROR
            )
        
        # Invertir imagen si está configurado
        if self.invertir:
            img = img.rotate(180)
        
        # Convertir a RGB565
        rgb565_data = image_to_rgb565(img)
        
        # Log de diagnóstico (solo cada 10 frames)
        if self._frame_count % 10 == 1:
            non_zero = sum(1 for b in rgb565_data[:5000] if b != 0)
            logger.debug(f"🖼️ Frame {self._frame_count}: {len(rgb565_data)} bytes, {non_zero}/5000 no-cero")
        
        return rgb565_data


class StatusScreenRunner:
    """Ejecuta la pantalla de estado en un thread separado."""
    
    def __init__(self, display_callback: Callable[[bytes], None], invertir: bool = False):
        """
        Args:
            display_callback: Función para enviar frames al display
            invertir: Si True, invierte la imagen 180°
        """
        self.display_callback = display_callback
        self.status_screen = StatusScreen(invertir=invertir)
        
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False
    
    def set_connection_status(self, connected: bool, host: str = "", port: int = 0):
        """Actualiza el estado de conexión."""
        self.status_screen.set_connection_status(connected, host, port)
    
    def start(self):
        """Inicia la pantalla de estado."""
        if self._running:
            return
        
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="StatusScreen"
        )
        self._thread.start()
        logger.info("🤖 Pantalla de estado iniciada")
    
    def stop(self):
        """Detiene la pantalla de estado (no bloqueante)."""
        if not self._running:
            return
        
        self._running = False
        self._stop_event.set()
        
        # No esperamos al thread - simplemente marcamos que debe parar
        # El thread terminará en su próximo ciclo
        logger.info("🤖 Pantalla de estado detenida")
    
    def _run_loop(self):
        """Loop principal que actualiza la pantalla cada segundo."""
        while not self._stop_event.is_set():
            try:
                # Verificar stop antes de generar frame
                if self._stop_event.is_set():
                    break
                    
                frame = self.status_screen.generate_frame()
                
                # Verificar stop antes de escribir
                if self._stop_event.is_set():
                    break
                    
                result = self.display_callback(frame)
                if not result:
                    logger.warning(f"⚠️ Fallo escribiendo frame de estado al framebuffer")
            except Exception as e:
                logger.error(f"Error generando frame de estado: {e}", exc_info=True)
            
            # Esperar 1 segundo (verificando stop cada 100ms)
            for _ in range(10):
                if self._stop_event.is_set():
                    break
                time.sleep(0.1)


if __name__ == '__main__':
    # Test de generación de pantalla
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s.%(msecs)03d %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    screen = StatusScreen()
    screen.set_connection_status(True, "192.168.0.2", 8888)
    
    # Generar algunos frames de prueba
    for i in range(3):
        frame = screen.generate_frame()
        logger.info(f"Frame {i+1}: {len(frame)} bytes")
        time.sleep(0.5)
    
    # Test desconectado
    screen.set_connection_status(False)
    frame = screen.generate_frame()
    logger.info(f"Frame desconectado: {len(frame)} bytes")
    
    # Guardar imagen de prueba
    if PIL_AVAILABLE:
        img = Image.new('RGB', (SCREEN_WIDTH, SCREEN_HEIGHT), COLOR_BG)
        draw = ImageDraw.Draw(img)
        screen._draw_robot_face(draw, 30, 40, 280, 230)
        img.save("/tmp/robot_status_test.png")
        logger.info("Imagen de prueba guardada en /tmp/robot_status_test.png")
