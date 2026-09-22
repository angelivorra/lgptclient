#!/usr/bin/env python3
"""
Gestor de medios (imágenes y animaciones).

Responsabilidades:
- Mantener cache LRU de imágenes
- Cargar configuración de animaciones bajo demanda
- Proporcionar datos de imagen/animación al display_executor
"""
import json
import logging
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from collections import OrderedDict
from dataclasses import dataclass

logger = logging.getLogger("cliente.media")


@dataclass
class AnimationConfig:
    """Configuración de una animación."""
    cc: int
    value: int
    fps: int
    loop: bool
    max_delay: int
    pack_path: str
    index_path: str
    frames: List[Dict]
    width: int
    height: int
    bpp: int
    
    @property
    def frame_interval(self) -> float:
        """Intervalo entre frames en segundos."""
        return 1.0 / self.fps if self.fps > 0 else 0.033


class MediaManager:
    """Gestiona carga y cache de imágenes y animaciones."""
    
    def __init__(self, base_path: str, max_image_cache: int = 10):
        """
        Args:
            base_path: Directorio base donde están las imágenes
            max_image_cache: Máximo número de imágenes en cache
        """
        self.base_path = Path(base_path)
        self.max_image_cache = max_image_cache
        self._image_cache: OrderedDict[Tuple[int, int], bytes] = OrderedDict()
        
        self.stats = {
            'image_cache_hits': 0,
            'image_cache_misses': 0,
            'images_loaded': 0,
            'animations_loaded': 0,
            'errors': 0,
        }
        
        if not self.base_path.exists():
            logger.warning(f"⚠️  Directorio base no existe: {self.base_path}")
        else:
            logger.info(f"📁 MediaManager inicializado: {self.base_path}")
    
    def get_image(self, cc: int, value: int) -> Optional[bytes]:
        """
        Obtiene una imagen desde el cache o la carga del disco.
        
        Returns:
            Datos de la imagen en formato bin, o None si no existe
        """
        key = (cc, value)
        
        if key in self._image_cache:
            self.stats['image_cache_hits'] += 1
            self._image_cache.move_to_end(key)
            logger.debug(f"🖼️  Imagen {cc:03d}/{value:03d} desde cache")
            return self._image_cache[key]
        
        self.stats['image_cache_misses'] += 1
        image_path = self.base_path / f"{cc:03d}" / f"{value:03d}.bin"
        
        if not image_path.exists():
            if cc == 2:
                data = self._render_lyric_rgb565(value)
                if data:
                    self._add_to_cache(key, data)
                    return data
            logger.debug(f"❌ Imagen no encontrada: {image_path}")
            return None
        
        try:
            data = image_path.read_bytes()
            self.stats['images_loaded'] += 1
            logger.info(f"📥 Imagen cargada {cc:03d}/{value:03d} ({len(data)} bytes)")
            
            self._add_to_cache(key, data)
            return data
            
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"❌ Error cargando imagen {image_path}: {e}")
            return None
    
    def get_animation(self, cc: int, value: int) -> Optional[AnimationConfig]:
        """
        Carga configuración de una animación desde disco.
        
        Returns:
            AnimationConfig con toda la información, o None si no existe
        """
        anim_dir = self.base_path / f"{cc:03d}" / f"{value:03d}"
        
        if not anim_dir.is_dir():
            logger.debug(f"❌ Directorio de animación no existe: {anim_dir}")
            return None
        
        pack_path = anim_dir / "pack.bin"
        index_path = anim_dir / "pack.bin.index.json"
        config_path = anim_dir / "anim.cfg"
        
        if not pack_path.exists():
            logger.error(f"❌ pack.bin no encontrado en {anim_dir}")
            return None
        
        if not index_path.exists():
            logger.error(f"❌ pack.bin.index.json no encontrado en {anim_dir}")
            return None
        
        if not config_path.exists():
            logger.error(f"❌ anim.cfg no encontrado en {anim_dir}")
            return None
        
        try:
            with open(config_path, 'r') as f:
                anim_cfg = json.load(f)
            
            fps = anim_cfg.get('fps', 30)
            loop = anim_cfg.get('loop', True)
            max_delay = anim_cfg.get('max_delay', 2)
            
            with open(index_path, 'r') as f:
                index_data = json.load(f)
            
            width = index_data.get('width', 800)
            height = index_data.get('height', 480)
            bpp = index_data.get('bpp', 16)
            frames = index_data.get('entries', [])
            
            if not frames:
                logger.error(f"❌ No hay frames en index.json de {anim_dir}")
                return None
            
            self.stats['animations_loaded'] += 1
            logger.info(
                f"🎬 Animación cargada {cc:03d}/{value:03d}: "
                f"{len(frames)} frames @ {fps}fps, loop={loop}"
            )
            
            return AnimationConfig(
                cc=cc,
                value=value,
                fps=fps,
                loop=loop,
                max_delay=max_delay,
                pack_path=str(pack_path),
                index_path=str(index_path),
                frames=frames,
                width=width,
                height=height,
                bpp=bpp
            )
            
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"❌ Error cargando animación {anim_dir}: {e}")
            return None
    
    def is_animation(self, cc: int, value: int) -> bool:
        """Verifica si un CC/value es una animación."""
        anim_dir = self.base_path / f"{cc:03d}" / f"{value:03d}"
        return anim_dir.is_dir()

    def load_fondo_images(self, name: str, width: int = 800,
                          height: int = 480) -> List[bytes]:
        """Carga todas las PNGs de images/fondos/{name}/ y las convierte a
        RGB565 (formato del framebuffer). Requiere Pillow; si no está
        disponible, intenta cargar .bin pre-convertidos con el mismo nombre.
        Devuelve lista de bytes lista para set_slideshow()."""
        fondo_dir = self.base_path / "fondos" / name
        if not fondo_dir.is_dir():
            logger.warning(f"⚠️  Carpeta de fondo no encontrada: {fondo_dir}")
            return []
        try:
            from PIL import Image as _PILImage
            _pil_ok = True
        except ImportError:
            _pil_ok = False

        result: List[bytes] = []
        pngs = sorted(fondo_dir.glob("*.png"))
        if not pngs:
            logger.warning(f"⚠️  No hay PNGs en {fondo_dir}")
            return []

        for png_path in pngs:
            if _pil_ok:
                try:
                    img = _PILImage.open(png_path).convert("RGB")
                    img = img.resize((width, height), _PILImage.LANCZOS)
                    pixels = img.tobytes()
                    # RGB888 → RGB565 (little-endian, igual que el resto)
                    import struct
                    out = bytearray(width * height * 2)
                    for i in range(width * height):
                        r, g, b = pixels[i*3], pixels[i*3+1], pixels[i*3+2]
                        v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                        struct.pack_into("<H", out, i * 2, v)
                    result.append(bytes(out))
                    logger.debug(f"🖼️  Fondo frame: {png_path.name}")
                except Exception as e:
                    logger.error(f"❌ Error cargando {png_path}: {e}")
            else:
                # Sin PIL: busca .bin pre-convertido junto al PNG
                bin_path = png_path.with_suffix(".bin")
                if bin_path.exists():
                    result.append(bin_path.read_bytes())
                else:
                    logger.warning(f"⚠️  Sin PIL y sin .bin para {png_path.name}")

        logger.info(f"🎞️  Fondo '{name}': {len(result)} frames cargados")
        return result
    
    def _render_lyric_rgb565(self, value: int,
                             width: int = 800, height: int = 480) -> Optional[bytes]:
        """Renderiza on-the-fly la línea `value` de images/002/textos a RGB565.

        Usa images/002/fondo.png como fondo y images/002/fuente*.ttf como tipo.
        Requiere Pillow. Si no está disponible o no hay textos, devuelve None.
        """
        textos_path = self.base_path / "002" / "textos"
        if not textos_path.exists():
            return None
        try:
            from PIL import Image as _PILImage, ImageDraw, ImageFont
        except ImportError:
            logger.warning("⚠️  PIL no disponible — textos no se pueden renderizar")
            return None
        try:
            lines = [l.strip() for l in textos_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            idx = max(0, value)  # 0-based, igual que lgpt_engine
            if idx >= len(lines):
                return None
            text = lines[idx]

            fondo_path = self.base_path / "002" / "fondo.png"
            if fondo_path.exists():
                img = _PILImage.open(fondo_path).convert("RGB").resize((width, height), _PILImage.LANCZOS)
            else:
                img = _PILImage.new("RGB", (width, height), (0, 0, 0))

            draw = ImageDraw.Draw(img)
            font_size = max(40, height // 6)
            font = None
            for fname in ("fuente22.ttf", "fuente2.ttf", "fuente.ttf"):
                fp = self.base_path / "002" / fname
                if fp.exists():
                    try:
                        font = ImageFont.truetype(str(fp), font_size)
                        break
                    except Exception:
                        continue
            if font is None:
                font = ImageFont.load_default()

            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            x, y = (width - tw) // 2, (height - th) // 2
            draw.text((x, y), text, fill=(255, 255, 255), font=font)

            import struct
            pixels = img.tobytes()
            out = bytearray(width * height * 2)
            for i in range(width * height):
                r, g, b = pixels[i * 3], pixels[i * 3 + 1], pixels[i * 3 + 2]
                v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                struct.pack_into("<H", out, i * 2, v)
            logger.info(f"📝 Texto CC=2/{value}: \"{text}\"")
            return bytes(out)
        except Exception as e:
            logger.error(f"❌ Error renderizando texto CC=2/{value}: {e}")
            return None

    def _add_to_cache(self, key: Tuple[int, int], data: bytes):
        """Agrega una imagen al cache LRU."""
        if key in self._image_cache:
            self._image_cache.move_to_end(key)
            self._image_cache[key] = data
            return
        
        if len(self._image_cache) >= self.max_image_cache:
            oldest_key = next(iter(self._image_cache))
            self._image_cache.pop(oldest_key)
            logger.debug(f"🗑️  Cache lleno: eliminada {oldest_key[0]:03d}/{oldest_key[1]:03d}")
        
        self._image_cache[key] = data
    
    def preload_image(self, cc: int, value: int):
        """Pre-carga una imagen en cache."""
        self.get_image(cc, value)
    
    def clear_cache(self):
        """Limpia el cache de imágenes."""
        count = len(self._image_cache)
        self._image_cache.clear()
        logger.info(f"🗑️  Cache limpiado: {count} imágenes eliminadas")
    
    def get_stats(self) -> dict:
        """Retorna estadísticas del gestor."""
        return {
            **self.stats,
            'cache_size': len(self._image_cache),
            'cache_max': self.max_image_cache,
        }
