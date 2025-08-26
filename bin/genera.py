import argparse
import logging
import time
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Dict, List, Optional, Any
import struct
from array import array
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import shutil

"""genera.py
Estructura esperada dentro de images/ :
  images/
    001/
       fondo.png
       fuente.ttf
       png/            (imagenes sueltas a colocar en centro)  (CarpetaTipo.IMAGENES)
       textos          (archivo o carpeta marcador)            (CarpetaTipo.TEXTOS)
       <subcarpetas>   (si no hay png/ ni textos => animaciones) (CarpetaTipo.ANIMACIONES)
    002/
       fondo.png fuente.ttf textos
    003/
       anim1/ anim2/ ... (sin fondo/fuente/textos => animaciones)

Reglas de detección (en orden):
  1. Si existe un archivo o carpeta llamada "textos" => TEXTOS
  2. Else si existen fondo.png y fuente.ttf => IMAGENES (colocar los png de subcarpetas png/ centrados)
  3. Else => ANIMACIONES (cada subcarpeta con frames PNG -> animación)

El output debe mantener la misma jerarquía numérica dentro de una carpeta destino (por ahora reuse dentro de cada carpeta se generan sus salidas en subcarpetas locales: salida/png y salida/bin por claridad).
"""

# -----------------------------------------------------------
# Logging
# -----------------------------------------------------------
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# -----------------------------------------------------------
# Configuración específica por terminal (extensible)
# -----------------------------------------------------------
DATOS_TERMINAL: Dict[str, Dict[str, Any]] = {
    "sombrilla": {"invert": True},
    "maleta": {"invert": False},
}

# Config en uso durante la ejecución (se setea en main)
CURRENT_CONFIG: Dict[str, Any] = {}
OUTPUT_BASE = Path('/home/angel/img_output')  # Salida principal solicitada
ANIM_CONFIG_FILENAME = 'anim.cfg'  # Archivo esperado dentro de cada carpeta de animación


class Cartera(Enum):  # alias semántico (evita conflicto con folder) (unused but placeholder)
    pass

class CarpetaTipo(Enum):
    TEXTOS = auto()
    IMAGENES = auto()
    ANIMACIONES = auto()


@dataclass
class ProcesamientoResultado:
    tipo: CarpetaTipo
    carpeta: Path
    detalles: Dict
    elapsed: float


# -----------------------------------------------------------
# Utilidades
# -----------------------------------------------------------
def vacia_carpeta(path: Path):
    if not path.exists():
        return
    for item in path.iterdir():
        try:
            if item.is_file():
                item.unlink()
            else:
                shutil.rmtree(item)
        except Exception as e:
            logger.warning(f"No se pudo eliminar {item}: {e}")


def note_from_index(index: int) -> str:
    return f"{index:02X}"  # 01..FF


def png_to_bin(img: Image.Image, bin_path: Path, width: int = 800, height: int = 480, bpp: int = 16):
    img = img.resize((width, height))
    img = img.convert("RGB")
    if bpp == 16:  # RGB565 optimizado
        pixels = img.getdata()
        buff = array('H', (( (r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3) for r, g, b in pixels ))
        # Asegurar little-endian
        if struct.pack('H', 1) == b'\x00\x01':  # big endian
            buff.byteswap()
        data = buff.tobytes()
    elif bpp == 24:
        data = img.tobytes()
    elif bpp == 32:
        data = img.convert("RGBA").tobytes()
    else:
        raise ValueError("bpp no soportado")
    bin_path.parent.mkdir(parents=True, exist_ok=True)
    with open(bin_path, 'wb') as f:
        f.write(data)


# -----------------------------------------------------------
# Detección de tipo de carpeta (extensible)
# -----------------------------------------------------------
FolderClassifier = Callable[[Path], Optional[CarpetaTipo]]


def classifier_textos(path: Path) -> Optional[CarpetaTipo]:
    if (path / 'textos').exists():
        return CarpetaTipo.TEXTOS
    return None


def classifier_imagenes(path: Path) -> Optional[CarpetaTipo]:
    if (path / 'fondo.png').exists() and (path / 'fuente.ttf').exists():
        return CarpetaTipo.IMAGENES
    return None


def classifier_animaciones(_: Path) -> Optional[CarpetaTipo]:
    return CarpetaTipo.ANIMACIONES  # fallback


CLASSIFIERS: List[FolderClassifier] = [
    classifier_textos,
    classifier_imagenes,
    classifier_animaciones,
]


def detectar_tipo_carpeta(path: Path) -> CarpetaTipo:
    for clf in CLASSIFIERS:
        tipo = clf(path)
        if tipo is not None:
            logger.debug(f"detectar_tipo_carpeta: {path.name} -> {tipo.name} (por {clf.__name__})")
            return tipo
    logger.debug(f"detectar_tipo_carpeta: {path.name} -> ANIMACIONES (fallback)")
    return CarpetaTipo.ANIMACIONES


# -----------------------------------------------------------
# Procesadores por tipo
# -----------------------------------------------------------
def procesa_textos(path: Path) -> Dict:
    """Genera imágenes de texto usando fondo.png & fuente.ttf.
    Lista de palabras fija de ejemplo (puede venir de archivo 'textos')."""
    fondo = path / 'fondo.png'
    fuente = path / 'fuente.ttf'
    textos_path = path / 'textos'
    if textos_path.is_file():
        palabras = [l.strip() for l in textos_path.read_text(encoding='utf-8').splitlines() if l.strip()]
    else:
        palabras = ["Demo", "Texto", "Ejemplo"]
    if not fondo.exists() or not fuente.exists():
        raise FileNotFoundError("Faltan fondo.png o fuente.ttf para textos")
    bg = Image.open(fondo).convert('RGBA')
    W, H = bg.size
    
    out_dir = OUTPUT_BASE / CURRENT_CONFIG.get('terminal', 'default') / path.name 
    vacia_carpeta(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    margin_ratio = 0.1
    max_w = W * (1 - 2 * margin_ratio)
    max_h = H * (1 - 2 * margin_ratio)
    invert = bool(CURRENT_CONFIG.get("invert"))
    for idx, palabra in enumerate(palabras):
        font_size = int(min(max_w, max_h))
        while font_size > 1:
            font = ImageFont.truetype(str(fuente), font_size)
            draw_tmp = ImageDraw.Draw(bg)
            bbox = draw_tmp.textbbox((0, 0), palabra, font=font)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            if w <= max_w and h <= max_h:
                break
            font_size -= 2
        canvas = bg.copy()
        stroke_width = 8
        draw = ImageDraw.Draw(canvas)
        bbox = draw.textbbox((0, 0), palabra, font=font, stroke_width=stroke_width)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = (W - w) // 2 - bbox[0]
        y = (H - h) // 2 - bbox[1]
        glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        dg = ImageDraw.Draw(glow)
        dg.text((x, y), palabra, font=font, fill='white', stroke_width=stroke_width, stroke_fill='white')
        glow = glow.filter(ImageFilter.GaussianBlur(radius=6))
        alpha = glow.getchannel('A').point(lambda a: int(a * 0.5))
        glow.putalpha(alpha)
        canvas = Image.alpha_composite(canvas, glow)
        draw2 = ImageDraw.Draw(canvas)
        draw2.text((x, y), palabra, font=font, fill='white')
        if invert:
            canvas = canvas.transpose(Image.FLIP_TOP_BOTTOM).transpose(Image.FLIP_LEFT_RIGHT)
        filename = f"{255 - idx:03d}.png"  # replicar patrón inverso
        png_path = out_dir / filename
        canvas.save(png_path)
        # Generar bin paralelo
        try:
            bin_path = out_dir / f"{png_path.stem}.bin"
            png_to_bin(canvas, bin_path)
        except Exception as e:
            logger.warning(f"No se pudo crear bin para texto {png_path.name}: {e}")
    return {"palabras": len(palabras), "out": str(out_dir)}


def procesa_imagenes(path: Path) -> Dict:
    """Centra cada png dentro de fondo usando fuente solo para consistencia (no se usa)."""
    fondo = path / 'fondo.png'
    if not fondo.exists():
        raise FileNotFoundError("fondo.png requerido")
    bg = Image.open(fondo).convert('RGBA')
    W, H = bg.size
    png_dir = path / 'png'
    if not png_dir.exists():
        return {"procesadas": 0, "razon": "No existe png/"}
    # Salida: /home/angel/img_output/<terminal>/<XXX>/
    out_dir = OUTPUT_BASE / CURRENT_CONFIG.get('terminal', 'default') / path.name
    vacia_carpeta(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    margin_ratio = 0.10
    max_w = W * (1 - 2 * margin_ratio)
    max_h = H * (1 - 2 * margin_ratio)
    procesadas = 0
    existentes = 0
    invert = bool(CURRENT_CONFIG.get("invert"))
    for i in range(1, 1000):
        src = png_dir / f"{i:03d}.png"
        if not src.exists():
            continue
        existentes += 1
        try:
            fg = Image.open(src).convert('RGBA')
            ow, oh = fg.size
            scale = min(max_w / ow, max_h / oh)
            new_size = (max(1, int(ow * scale)), max(1, int(oh * scale)))
            if new_size != (ow, oh):
                fg = fg.resize(new_size, Image.LANCZOS)
            lienzo = bg.copy()
            nw, nh = fg.size
            x = (W - nw) // 2
            y = (H - nh) // 2
            lienzo.alpha_composite(fg, dest=(x, y))
            if invert:
                lienzo = lienzo.transpose(Image.FLIP_TOP_BOTTOM).transpose(Image.FLIP_LEFT_RIGHT)
            png_dest = out_dir / f"{i:03d}.png"
            bin_dest = out_dir / f"{i:03d}.bin"
            lienzo.save(png_dest)
            # Generar bin directamente
            try:
                png_to_bin(lienzo, bin_dest)
            except Exception as e:
                logger.error(f"Error generando bin {bin_dest.name}: {e}")
            procesadas += 1
        except Exception as e:
            logger.error(f"Error procesando {src}: {e}")
    return {"procesadas": procesadas, "existentes": existentes, "out": str(out_dir)}


def procesa_animaciones(path: Path) -> Dict:
    """Cada subcarpeta => animación, frames *.png -> se exportan centrados en canvas 800x480 si posible."""
    subdirs = [d for d in path.iterdir() if d.is_dir()]
    configs_copiados = 0
    # Salida: /home/angel/img_output/<terminal>/<XXX>/animaciones/<animacion>/
    base_out = OUTPUT_BASE / CURRENT_CONFIG.get('terminal', 'default') / path.name
    vacia_carpeta(base_out)
    base_out.mkdir(parents=True, exist_ok=True)
    animaciones = 0
    frames_total = 0
    invert = bool(CURRENT_CONFIG.get("invert"))
    for d in subdirs:
        frames = sorted(d.glob('*.png'))
        if not frames:
            continue
        animaciones += 1
        anim_dir = base_out / d.name
        anim_dir.mkdir(parents=True, exist_ok=True)
        # Copiar archivo de config si existe
        cfg_src = d / ANIM_CONFIG_FILENAME
        if cfg_src.exists() and cfg_src.is_file():
            try:
                shutil.copy2(cfg_src, anim_dir / ANIM_CONFIG_FILENAME)
                configs_copiados += 1
            except Exception as e_cfg:
                logger.warning(f"No se pudo copiar config {cfg_src}: {e_cfg}")
        for idx, frame in enumerate(frames):
            try:
                img = Image.open(frame).convert('RGBA')
                img = img.resize((800, 480))
                if invert:
                    img = img.transpose(Image.FLIP_TOP_BOTTOM).transpose(Image.FLIP_LEFT_RIGHT)
                frame_num = idx + 1  # 1-based
                bin_dest = anim_dir / f"{frame_num:03d}.bin"
                png_dest = anim_dir / f"{frame_num:03d}.png"
                # Guardar PNG (copia del frame normalizado)
                try:
                    img.save(png_dest)
                except Exception as e_png:
                    logger.error(f"Error guardando PNG {png_dest}: {e_png}")
                png_to_bin(img, bin_dest)
                if frame_num % 25 == 0 or frame_num == len(frames):
                    logger.debug(f"Anim {d.name}: frame {frame_num}/{len(frames)}")
                frames_total += 1
            except Exception as e:
                logger.error(f"Frame {frame} error: {e}")
    return {"animaciones": animaciones, "frames": frames_total, "configs": configs_copiados, "out": str(base_out)}


PROCESSORS: Dict[CarpetaTipo, Callable[[Path], Dict]] = {
    CarpetaTipo.TEXTOS: procesa_textos,
    CarpetaTipo.IMAGENES: procesa_imagenes,
    CarpetaTipo.ANIMACIONES: procesa_animaciones,
}


def procesa_carpeta(carpeta: Path) -> ProcesamientoResultado:
    t0 = time.perf_counter()
    tipo = detectar_tipo_carpeta(carpeta)
    logger.info(f"Carpeta {carpeta.name} -> {tipo.name}")
    detalles = PROCESSORS[tipo](carpeta)
    elapsed = time.perf_counter() - t0
    return ProcesamientoResultado(tipo=tipo, carpeta=carpeta, detalles=detalles, elapsed=elapsed)


def recorrer_images(root: Path) -> List[ProcesamientoResultado]:
    resultados: List[ProcesamientoResultado] = []
    logger.debug(f"Explorando root: {root}")
    for sub in sorted(root.iterdir()):
        if not sub.is_dir():
            logger.debug(f"Ignorado (no dir): {sub.name}")
            continue
        if not sub.name.isdigit():
            logger.debug(f"Ignorado (nombre no numérico): {sub.name}")
            continue
        logger.debug(f"Procesando subcarpeta candidata: {sub.name}")
        resultados.append(procesa_carpeta(sub))
    if not resultados:
        logger.info(f"No se encontraron subcarpetas numéricas dentro de {root}")
    return resultados


def main():
    parser = argparse.ArgumentParser(description='Generador nuevo estructura por terminal')
    parser.add_argument('terminal', help=f"Terminal destino ({', '.join(DATOS_TERMINAL.keys())})")
    parser.add_argument('--images-root', default='/home/angel/lgptclient/images', help='Ruta base images/')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--markdown', action='store_true', help='Generar guías markdown en ayuda_imagenes/')
    args = parser.parse_args()
    terminal = args.terminal.lower()
    if terminal not in DATOS_TERMINAL:
        raise SystemExit(f"Terminal desconocido: {terminal}. Opciones: {', '.join(DATOS_TERMINAL)}")
    global CURRENT_CONFIG
    CURRENT_CONFIG = dict(DATOS_TERMINAL[terminal])  # copia
    CURRENT_CONFIG['terminal'] = terminal
    if args.debug:
        logger.setLevel(logging.DEBUG)
    images_root = Path(args.images_root)
    if not images_root.exists():
        raise SystemExit(f"No existe: {images_root}")
    # Limpiar carpeta de salida del terminal antes de generar
    terminal_output_dir = Path('/home/angel/img_output') / terminal
    if terminal_output_dir.exists():
        logger.info(f"Vaciando salida previa: {terminal_output_dir}")
        vacia_carpeta(terminal_output_dir)
    terminal_output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Procesando root: {images_root} para terminal '{terminal}' (invert={CURRENT_CONFIG.get('invert')})")
    logger.debug(f"CONFIG ACTUAL: {CURRENT_CONFIG}")
    t0 = time.perf_counter()
    resultados = recorrer_images(images_root)
    # Generar markdown si se solicita
    if args.markdown:
        try:
            generar_markdown_ayuda(resultados)
        except Exception as e:
            logger.error(f"Error generando markdown de ayuda: {e}")
    total = time.perf_counter() - t0
    logger.info("Resumen:")
    for r in resultados:
        logger.info(f"  {r.carpeta.name}: {r.tipo.name} {r.detalles} ({r.elapsed:.2f}s)")
    if not resultados:
        logger.info("No hubo resultados que resumir (0 carpetas procesadas)")
    logger.info(f"Tiempo total: {total:.2f}s")


# -----------------------------------------------------------
# Markdown de ayuda
# -----------------------------------------------------------
def generar_markdown_ayuda(resultados: List[ProcesamientoResultado]):
    """Genera 001.md, 002.md, ... en /home/angel/lgptclient/ayuda_imagenes/
    Copiando también los PNG necesarios para visualizarlos.
    Para carpetas IMAGENES / TEXTOS: lista de miniaturas.
    Para ANIMACIONES: se listan animaciones y frames.
    """
    ayuda_root = Path('/home/angel/lgptclient/ayuda_imagenes')
    ayuda_root.mkdir(parents=True, exist_ok=True)
    terminal = CURRENT_CONFIG.get('terminal', 'default')
    for res in resultados:
        carpeta_id = res.carpeta.name  # '001', '002', ...
        md_path = ayuda_root / f"{carpeta_id}.md"
        salida_dir = OUTPUT_BASE / terminal / carpeta_id
        if not salida_dir.exists():
            logger.warning(f"Salida no encontrada para {carpeta_id}, se omite markdown")
            continue
        # Directorio local para copiar assets: ayuda_imagenes/<carpeta_id>/
        assets_dir = ayuda_root / carpeta_id
        if assets_dir.exists():
            vacia_carpeta(assets_dir)
        assets_dir.mkdir(parents=True, exist_ok=True)
        secciones: List[str] = [f"# Carpeta {carpeta_id}", f"Tipo: {res.tipo.name}"]
        if res.tipo == CarpetaTipo.IMAGENES or res.tipo == CarpetaTipo.TEXTOS:
            pngs = sorted(p for p in salida_dir.glob('*.png'))
            filas = []
            columnas = 5
            row = []
            for idx, png in enumerate(pngs, 1):
                destino_png = assets_dir / png.name
                try:
                    shutil.copy2(png, destino_png)
                except Exception as e:
                    logger.warning(f"No se pudo copiar {png}: {e}")
                rel = f"{carpeta_id}/{png.name}"
                row.append(f"<td align='center' style='font-family:monospace;font-size:14px'>{png.stem}<br><img src='{rel}' width='240'/></td>")
                if len(row) == columnas:
                    filas.append('<tr>' + ''.join(row) + '</tr>')
                    row = []
            if row:
                while len(row) < columnas:
                    row.append('<td></td>')
                filas.append('<tr>' + ''.join(row) + '</tr>')
            secciones.append('<table>')
            secciones.extend(filas)
            secciones.append('</table>')
        elif res.tipo == CarpetaTipo.ANIMACIONES:
            # Subcarpetas = animaciones
            anims = [d for d in salida_dir.iterdir() if d.is_dir()]
            for anim in sorted(anims):
                secciones.append(f"\n## Animación {anim.name}")
                anim_assets_dir = assets_dir / anim.name
                anim_assets_dir.mkdir(parents=True, exist_ok=True)
                frames = sorted(anim.glob('*.png'))
                if not frames:
                    secciones.append("(Sin frames PNG)")
                    continue
                filas = []
                columnas = 8
                row = []
                for i, frame in enumerate(frames, 1):
                    destino_png = anim_assets_dir / frame.name
                    try:
                        shutil.copy2(frame, destino_png)
                    except Exception as e:
                        logger.warning(f"No se pudo copiar frame {frame}: {e}")
                    rel = f"{carpeta_id}/{anim.name}/{frame.name}"
                    row.append(f"<td style='padding:2px;font-size:12px;font-family:monospace'>{frame.stem}<br><img src='{rel}' width='120'/></td>")
                    if len(row) == columnas:
                        filas.append('<tr>' + ''.join(row) + '</tr>')
                        row = []
                if row:
                    while len(row) < columnas:
                        row.append('<td></td>')
                    filas.append('<tr>' + ''.join(row) + '</tr>')
                secciones.append('<table>')
                secciones.extend(filas)
                secciones.append('</table>')
        md_path.write_text('\n\n'.join(secciones), encoding='utf-8')
        logger.info(f"Markdown ayuda generado: {md_path}")

if __name__ == '__main__':
    main()

