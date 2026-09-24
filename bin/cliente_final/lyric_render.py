"""Pinta una línea del banco 002: Tilt Neon como tubo de neón + glow.

Usado por ``bin/genera.py`` (bins/thumbs) y por el fallback del cliente
(``media_manager``) para que el look sea el mismo en PC y en la Pi.
"""
from __future__ import annotations

import random
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

TEMAS_ROBOT: Tuple[Tuple[int, int, int], ...] = (
    (0, 229, 255),    # cian
    (57, 255, 20),    # verde matrix
    (255, 176, 0),    # ámbar
    (255, 45, 45),    # rojo alerta
    (255, 0, 200),    # magenta
    (120, 200, 255),  # hielo
    (180, 120, 255),  # violeta
)

SCREEN_W = 800
SCREEN_H = 480


def find_fuente(bank_dir: Path) -> Optional[Path]:
    p = Path(bank_dir) / "fuente.ttf"
    return p if p.is_file() else None


def _tema_palabra(rng: random.Random) -> Tuple[int, int, int]:
    return rng.choice(TEMAS_ROBOT)


def _stroke_width(font_size: int) -> int:
    """Grosor del tubo. Fino para que los huecos (B, e) no se tapen."""
    return max(7, int(round(font_size / 24)))


def _fit_font(fuente: Path, palabra: str, max_w: float, max_h: float
              ) -> Tuple[ImageFont.FreeTypeFont, int, int]:
    font_size = int(min(max_w, max_h))
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    font = ImageFont.truetype(str(fuente), max(1, font_size))
    sw = _stroke_width(font_size)
    while font_size > 1:
        font = ImageFont.truetype(str(fuente), font_size)
        sw = _stroke_width(font_size)
        bbox = probe.textbbox((0, 0), palabra, font=font, stroke_width=sw)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        if w <= max_w and h <= max_h:
            break
        font_size -= 2
    return font, font_size, sw


def _texto(size: Tuple[int, int], xy: Tuple[int, int], palabra: str,
           font: ImageFont.FreeTypeFont, fill, stroke_width: int) -> Image.Image:
    """Contorno = tubo de neón. Fill transparente: Tilt Neon relleno parece sans."""
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text(
        xy, palabra, font=font,
        fill=(0, 0, 0, 0),
        stroke_width=stroke_width,
        stroke_fill=fill,
    )
    return layer


def _mezcla(color: Tuple[int, int, int], t: float) -> Tuple[int, int, int, int]:
    """t=0 color puro, t=1 blanco."""
    r, g, b = color
    return (
        min(255, int(r + (255 - r) * t)),
        min(255, int(g + (255 - g) * t)),
        min(255, int(b + (255 - b) * t)),
        255,
    )


def _survive_composite(rgba: np.ndarray) -> np.ndarray:
    """Cola oscura del blur → transparente (si no, pastilla negra sobre el
    slideshow). Halo cian lum≤25 se sube para que no lo coma la rejilla."""
    rgb_sum = (rgba[:, :, 0].astype(np.uint16)
               + rgba[:, :, 1] + rgba[:, :, 2])
    rgba[rgb_sum < 70] = (0, 0, 0, 255)

    r5 = rgba[:, :, 0].astype(np.uint16) >> 3
    g6 = rgba[:, :, 1].astype(np.uint16) >> 2
    b5 = rgba[:, :, 2].astype(np.uint16) >> 3
    lum = r5 + g6 + b5
    eaten = (lum > 0) & (b5 > r5) & (lum <= 25)
    if eaten.any():
        rgb = rgba[:, :, :3][eaten].astype(np.int16)
        rgba[:, :, :3][eaten] = np.clip(rgb * 2 + 64, 0, 255).astype(np.uint8)
    return rgba


def render_lyric_rgba(text: str, font_path: Path,
                      width: int = SCREEN_W, height: int = SCREEN_H) -> Image.Image:
    """Tilt Neon hueco a tamaño de título, glow de tubo, fondo negro = slideshow."""
    palabra = text
    max_w = width * 0.96
    max_h = height * 0.70
    font, _font_size, sw = _fit_font(font_path, palabra, max_w, max_h)

    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    probe = ImageDraw.Draw(canvas)
    bbox = probe.textbbox((0, 0), palabra, font=font, stroke_width=sw)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    x = (width - w) // 2 - bbox[0]
    y = (height - h) // 2 - bbox[1]

    rng = random.Random(palabra)
    color = _tema_palabra(rng)
    xy = (x, y)
    size = (width, height)

    # Corona brillante y un blur corto: el composite es opaco/transparente,
    # un blur ancho se lee como mancha negra sobre el fondo.
    halo = _texto(size, xy, palabra, font, color + (255,), sw + 4)
    halo = halo.filter(ImageFilter.GaussianBlur(radius=5))
    canvas = Image.alpha_composite(canvas, halo)

    corona = _texto(size, xy, palabra, font, color + (255,), sw + 2)
    corona = corona.filter(ImageFilter.GaussianBlur(radius=2))
    canvas = Image.alpha_composite(canvas, corona)

    # Tubo en color de tema.
    canvas = Image.alpha_composite(
        canvas, _texto(size, xy, palabra, font, color + (255,), sw))

    # Núcleo caliente (más fino, más blanco) — eso se lee como neón, no como sans.
    core_w = max(3, sw - 4)
    canvas = Image.alpha_composite(
        canvas, _texto(size, xy, palabra, font, _mezcla(color, 0.72), core_w))

    return Image.fromarray(_survive_composite(np.array(canvas)), "RGBA")


def rgba_to_rgb565(img: Image.Image) -> bytes:
    """RGB565 little-endian, mismo empaquetado que ``genera.png_to_bin``."""
    arr = np.asarray(img.convert("RGB"), dtype=np.uint16)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    rgb565 = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    return rgb565.astype("<u2").tobytes()
