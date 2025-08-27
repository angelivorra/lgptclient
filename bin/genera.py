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
import json

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
OUTPUT_BASE = Path('/home/angel/lgptclient/img_output')  # Salida principal solicitada
HELP_BASE = Path('/home/angel/lgptclient/ayuda_imagenes')  # Thumbnails + markdown
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


def crear_pack(bin_paths: List[Path], out_dir: Path, pack_name: str = 'pack.bin', remove_bins: bool = True) -> Dict[str, Any]:
    """Concatena binarios (frames) en un único archivo pack.bin y genera un índice JSON.
    Estructura:
      pack.bin: concatenación cruda en el orden dado.
      pack.bin.index.json: {
         "width":800,"height":480,"bpp":16,
         "entries":[{"file":"001.bin","offset":0,"size":768000}, ...]
      }
    remove_bins: si True elimina los .bin originales para reducir inodos / lecturas.
    Devuelve dict resumen para logs.
    """
    if not bin_paths:
        return {"pack": None, "entries": 0}
    pack_path = out_dir / pack_name
    index_path = out_dir / f"{pack_name}.index.json"
    offset = 0
    entries: List[Dict[str, Any]] = []
    try:
        with open(pack_path, 'wb') as fout:
            for bp in bin_paths:
                if not bp.exists():
                    logger.warning(f"Saltando faltante para pack: {bp.name}")
                    continue
                size = bp.stat().st_size
                with open(bp, 'rb') as fin:
                    shutil.copyfileobj(fin, fout)
                entries.append({
                    "file": bp.name,
                    "offset": offset,
                    "size": size
                })
                offset += size
        meta = {"width": 800, "height": 480, "bpp": 16, "entries": entries}
        index_path.write_text(json.dumps(meta, indent=2), encoding='utf-8')
        logger.info(f"Pack creado: {pack_path} ({len(entries)} frames)")
        if remove_bins:
            for bp in bin_paths:
                try:
                    bp.unlink()
                except Exception as e_rm:
                    logger.debug(f"No se pudo borrar {bp.name}: {e_rm}")
        return {"pack": str(pack_path), "entries": len(entries)}
    except Exception as e:
        logger.error(f"Error creando pack en {out_dir}: {e}")
        return {"pack_error": str(e)}


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
    thumbs_dir = None
    if CURRENT_CONFIG.get('markdown'):
        thumbs_dir = HELP_BASE / path.name
        if thumbs_dir.exists():
            vacia_carpeta(thumbs_dir)
        thumbs_dir.mkdir(parents=True, exist_ok=True)
    margin_ratio = 0.1
    max_w = W * (1 - 2 * margin_ratio)
    max_h = H * (1 - 2 * margin_ratio)
    invert = bool(CURRENT_CONFIG.get("invert"))
    # Ya no se empaquetan textos (solo animaciones requieren pack único)
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
        # Numeración ascendente normal empezando en 000
        filename = f"{idx:03d}.png"
        # Generar bin paralelo (no guardamos PNG en output)
        try:
            bin_path = out_dir / f"{filename.split('.')[0]}.bin"
            png_to_bin(canvas, bin_path)
        except Exception as e:
            logger.warning(f"No se pudo crear bin para texto {filename}: {e}")
        if thumbs_dir is not None:
            try:
                prev = canvas.copy().convert('RGB')
                new_w = 300
                scale = new_w / prev.width
                new_h = int(prev.height * scale)
                prev = prev.resize((new_w, new_h))
                prev.save(thumbs_dir / filename)
            except Exception as e_prev:
                logger.warning(f"Miniatura texto fallo {filename}: {e_prev}")
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
    thumbs_dir = None
    if CURRENT_CONFIG.get('markdown'):
        thumbs_dir = HELP_BASE / path.name
        if thumbs_dir.exists():
            vacia_carpeta(thumbs_dir)
        thumbs_dir.mkdir(parents=True, exist_ok=True)
    margin_ratio = 0.10
    max_w = W * (1 - 2 * margin_ratio)
    max_h = H * (1 - 2 * margin_ratio)
    procesadas = 0
    existentes = 0
    invert = bool(CURRENT_CONFIG.get("invert"))
    # No se empaquetan imágenes individuales; solo animaciones
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
            bin_dest = out_dir / f"{i:03d}.bin"
            # Generar bin
            try:
                png_to_bin(lienzo, bin_dest)
            except Exception as e:
                logger.error(f"Error generando bin {bin_dest.name}: {e}")
            if thumbs_dir is not None:
                try:
                    prev = lienzo.copy().convert('RGB')
                    new_w = 300
                    scale = new_w / prev.width
                    new_h = int(prev.height * scale)
                    prev = prev.resize((new_w, new_h))
                    prev.save(thumbs_dir / f"{i:03d}.png")
                except Exception as e_prev:
                    logger.warning(f"Miniatura imagen fallo {i:03d}.png: {e_prev}")
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
    thumbs_root = None
    if CURRENT_CONFIG.get('markdown'):
        thumbs_root = HELP_BASE / path.name
        if thumbs_root.exists():
            vacia_carpeta(thumbs_root)
        thumbs_root.mkdir(parents=True, exist_ok=True)
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
        anim_thumbs = None
        if thumbs_root is not None:
            anim_thumbs = thumbs_root / d.name
            anim_thumbs.mkdir(parents=True, exist_ok=True)
        # Copiar archivo de config si existe
        cfg_src = d / ANIM_CONFIG_FILENAME
        if cfg_src.exists() and cfg_src.is_file():
            try:
                shutil.copy2(cfg_src, anim_dir / ANIM_CONFIG_FILENAME)
                configs_copiados += 1
            except Exception as e_cfg:
                logger.warning(f"No se pudo copiar config {cfg_src}: {e_cfg}")
        bin_paths: List[Path] = []
        for idx, frame in enumerate(frames):
            try:
                img = Image.open(frame).convert('RGBA')
                img = img.resize((800, 480))
                if invert:
                    img = img.transpose(Image.FLIP_TOP_BOTTOM).transpose(Image.FLIP_LEFT_RIGHT)
                # Numeración desde 000
                frame_num = idx  # 0-based -> 000,001,...
                bin_dest = anim_dir / f"{frame_num:03d}.bin"
                png_to_bin(img, bin_dest)
                bin_paths.append(bin_dest)
                if anim_thumbs is not None:
                    try:
                        prev = img.copy().convert('RGB')
                        new_w = 300
                        scale = new_w / prev.width
                        new_h = int(prev.height * scale)
                        prev = prev.resize((new_w, new_h))
                        prev.save(anim_thumbs / f"{frame_num:03d}.png")
                    except Exception as e_prev:
                        logger.warning(f"Miniatura frame fallo {frame_num:03d}: {e_prev}")
                # Progreso (humano) 1-based para legibilidad
                if (idx + 1) % 25 == 0 or (idx + 1) == len(frames):
                    logger.debug(f"Anim {d.name}: frame {idx + 1}/{len(frames)} (archivo {frame_num:03d}.bin)")
                frames_total += 1
            except Exception as e:
                logger.error(f"Frame {frame} error: {e}")
        # Crear pack
        if bin_paths:
            crear_pack(bin_paths, anim_dir, pack_name='pack.bin')
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
    # Propagar flag markdown para que los procesadores generen miniaturas
    if args.markdown:
        CURRENT_CONFIG['markdown'] = True
    # Empaquetado de animaciones siempre activo, no necesita flag
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
    """Genera 001.md, 002.md, ... usando miniaturas previamente creadas en HELP_BASE.
    No copia ni recrea PNGs; simplemente referencia las miniaturas.
    Para IMAGENES / TEXTOS: thumbnails en HELP_BASE/<carpeta>/xxx.png (300px de ancho aprox).
    Para ANIMACIONES: thumbnails en HELP_BASE/<carpeta>/<anim>/<frame>.png
    """
    def dec_stem_a_hex(stem: str) -> str:
        try:
            n = int(stem)
            if 0 <= n <= 255:
                return f"{n:02X}"          # 0..255 -> 00..FF
            return f"{n:X}"                # fuera de rango: hex sin padding
        except ValueError:
            return stem                     # no numérico, deja igual
    ayuda_root = HELP_BASE
    ayuda_root.mkdir(parents=True, exist_ok=True)
    for res in resultados:
        carpeta_id = res.carpeta.name
        thumbs_dir = ayuda_root / carpeta_id
        if not thumbs_dir.exists():
            logger.warning(f"No hay miniaturas para {carpeta_id}, se omite markdown")
            continue
        md_path = ayuda_root / f"{carpeta_id}.md"
        secciones: List[str] = [
            f"# Carpeta {carpeta_id}",
            f"Tipo: {res.tipo.name}",
            "_Nota:_ Etiquetas mostradas en HEX (00=0 decimal, FF=255)."
        ]
        if res.tipo in (CarpetaTipo.IMAGENES, CarpetaTipo.TEXTOS):
            pngs = sorted(p for p in thumbs_dir.glob('*.png'))
            filas = []
            columnas = 5
            row = []
            for png in pngs:
                carpeta_hex = f"{int(carpeta_id):02X}"
                stem_hex = f"{int(png.stem):02X}"
                etiqueta = f"{carpeta_hex}{stem_hex}"
                rel = f"{carpeta_id}/{png.name}"
                row.append(
                    f"<td align='center' style='font-family:monospace;font-size:14px'>{etiqueta}<br>"
                    f"<img src='{rel}' width='300'/></td>"
                )
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
            anims = [d for d in thumbs_dir.iterdir() if d.is_dir()]
            for anim in sorted(anims):
                carpeta_hex = f"{int(carpeta_id):02X}"
                stem_hex = f"{int(anim.name):02X}"
                etiqueta = f"{carpeta_hex}{stem_hex}" 
                secciones.append(f"\n## {etiqueta}")
                frames = sorted(anim.glob('*.png'))
                if not frames:
                    secciones.append('(Sin frames)')
                    continue
                filas = []
                columnas = 8
                row = []
                for frame in frames:
                    etiqueta = dec_stem_a_hex(frame.stem)
                    rel = f"{carpeta_id}/{anim.name}/{frame.name}"
                    row.append(
                        f"<td style='padding:2px;font-size:12px;font-family:monospace'>{etiqueta}<br>"
                        f"<img src='{rel}' width='120'/></td>"
                    )
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

