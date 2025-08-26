if __name__ == '__main__':
    main()
import argparse
from pathlib import Path
import shutil
import struct
import logging
import time
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from logging import getLogger, DEBUG, INFO

logger = getLogger(__name__)
if not logger.handlers:
    # Configuración básica solo si no hay handlers previos (evita duplicados si se importa)
    handler = logging.StreamHandler()
    formatter = logging.Formatter('[%(levelname)s] %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(INFO)

DATOS = {
    "sombrilla":{
        "invert": True
    },
        "maleta":{
        "invert": False
    }
}

ANIMATED_PNG_OUTPUT_FOLDER = "/home/angel/lgptclient/images/imagenes_pi"

def genera_imagenes_desde_subpng(margin_ratio: float = 0.10):
    """
    Recorre /home/angel/lgptclient/images/png buscando 001.png .. 255.png.
    Por cada archivo existente:
      * Carga el fondo /home/angel/lgptclient/images/fondo.png
      * Carga la imagen origen en RGBA
      * La redimensiona para que quepa dentro de un rectángulo cuyo margen es
        "margin_ratio" (10% por defecto) respecto al tamaño del fondo, manteniendo
        proporción y maximizando el tamaño posible.
      * Centra la imagen resultante (vertical y horizontal) sobre el fondo.
      * Guarda el resultado en /home/angel/lgptclient/images/XXX.png (mismo nombre)
    Devuelve estadísticas básicas.
    """
    base_dir = Path("/home/angel/lgptclient/images")
    src_dir = base_dir / "png"
    fondo_path = base_dir / "fondo.png"
    if not fondo_path.exists():
        logger.warning(f"Fondo no encontrado: {fondo_path}")
        return {"fase":"subpng","procesadas":0,"existentes":0,"elapsed":0.0}
    if not src_dir.exists():
        logger.info(f"No existe subcarpeta png: {src_dir}")
        return {"fase":"subpng","procesadas":0,"existentes":0,"elapsed":0.0}

    start = time.perf_counter()
    total_existentes = 0
    procesadas = 0
    fondo_base = Image.open(fondo_path).convert("RGBA")
    W, H = fondo_base.size
    max_w = W * (1 - 2 * margin_ratio)
    max_h = H * (1 - 2 * margin_ratio)

    logger.info("Generando imágenes desde subcarpeta png (001-255)...")
    for i in range(1, 256):
        nombre = f"{i:03d}.png"
        src_path = src_dir / nombre
        if not src_path.exists():
            continue
        total_existentes += 1
        try:
            fg = Image.open(src_path).convert("RGBA")
            ow, oh = fg.size
            # Factor de escalado máximo que respeta el margen
            scale = min(max_w / ow, max_h / oh)
            # Ajuste de seguridad por si la imagen ya es más pequeña (permitimos escalar hacia arriba si quiere maximizar)
            new_size = (max(1, int(ow * scale)), max(1, int(oh * scale)))
            if new_size != (ow, oh):
                fg = fg.resize(new_size, Image.LANCZOS)
            nw, nh = fg.size
            x = (W - nw) // 2
            y = (H - nh) // 2
            lienzo = fondo_base.copy()
            # Composición preservando alpha
            lienzo.alpha_composite(fg, dest=(x, y))
            dest_path = base_dir / nombre
            lienzo.save(dest_path)
            procesadas += 1
            if procesadas % 25 == 0:
                logger.info(f"  Procesadas {procesadas} imágenes desde subpng...")
        except Exception as e:
            logger.error(f"Error procesando {src_path.name}: {e}")

    elapsed = time.perf_counter() - start
    logger.info(f"Subcarpeta png: {procesadas}/{total_existentes} imágenes compuestas en {elapsed:.2f}s")
    return {"fase":"subpng","procesadas":procesadas,"existentes":total_existentes,"elapsed":elapsed}

def png_to_bin(input_img, bin_path, screenx, screeny, bpp=24):
    """
    Modified version that accepts both path and Image objects
    """
    # Handle both string paths and Image objects
    if isinstance(input_img, str):
        img = Image.open(input_img)
    else:
        img = input_img
        
    # Open the PNG image using Pillow
    img = Image.open(input_img)
    
    # Ensure the image matches the screen size (resize if necessary)
    img = img.resize((screenx, screeny))
    
    # Convert the image to RGB (for 16bpp, we use RGB565)
    img = img.convert("RGB")
    
    # If 16 bpp, we need to manually convert to RGB565 format
    if bpp == 16:
        img_data = []
        for r, g, b in img.getdata():
            # Pack the RGB values into RGB565 (5 bits red, 6 bits green, 5 bits blue)
            rgb565 = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
            img_data.append(struct.pack('<H', rgb565))  # Little-endian 2-byte format
        img_data = b''.join(img_data)
    else:
        # Convert the image to the desired format (RGB or RGBA depending on bpp)
        if bpp == 24:
            img = img.convert("RGB")
        elif bpp == 32:
            img = img.convert("RGBA")
        # Get the raw pixel data
        img_data = img.tobytes()

    # Save the raw data to a .bin file
    bin_path = Path(bin_path)
    bin_path.parent.mkdir(parents=True, exist_ok=True)
    with open(bin_path, "wb") as f:
        f.write(img_data)
    logger.debug(f"BIN guardado: {bin_path}")

def note_from_index(index):
    """
    Convierte un índice numérico a una cadena hexadecimal de dos dígitos.
    Por ejemplo: 1 -> '01', 10 -> '0A', 15 -> '0F', 16 -> '10', etc.
    """
    return f"{index:02X}"


def resize_png(source_png, dest_png, width=800, height=480):
    """
    Redimensiona una imagen PNG a 800x480 y la guarda en la ruta de destino.
    
    :param source_png: Ruta al archivo PNG de origen.
    :param dest_png: Ruta al archivo PNG de destino.
    :param width: Ancho de la imagen (por defecto 800).
    :param height: Alto de la imagen (por defecto 480).
    """
    dest_dir = Path(dest_png).parent
    dest_dir.mkdir(parents=True, exist_ok=True)    
    
    # Abrir la imagen PNG de origen
    img = Image.open(source_png)
    
    # Redimensionar la imagen a las dimensiones especificadas
    img_resized = img.resize((width, height))
    
    # Guardar la imagen redimensionada en la ruta de destino
    img_resized.save(dest_png)
    logger.debug(f"PNG redimensionado a {width}x{height}: {dest_png}")

def empty_folder(folder_path):
    """
    Delete all files in a folder without deleting the folder itself.
    
    :param folder_path: Path to the folder to be emptied.
    """
    folder = Path(folder_path)
    if folder.exists() and folder.is_dir():
        deleted = 0
        for file in folder.iterdir():
            try:
                if file.is_file():
                    file.unlink()
                elif file.is_dir():
                    shutil.rmtree(file)
                deleted += 1
            except Exception as e:
                logger.warning(f"No se pudo eliminar {file}: {e}")
        logger.info(f"Carpeta vaciada: {folder} (eliminados {deleted} entradas)")

def genera_imagenes_con_texto(terminal):
    terminal = terminal.lower()
    if terminal not in DATOS:
        raise ValueError(f"Terminal '{terminal}' no encontrado en DATOS")
        
    origin_folder = "/home/angel/lgptclient/images"  
    plantilla = "/home/angel/lgptclient/images/fondo.png"  
    font_path="/home/angel/lgptclient/images/NeonSans.ttf"
    palabras = ["We're", "charging", "our", "battery", "And now", "we're", "full of", "energy", "WE", "ARE", "THE", "ROBOTS", "No hay", "Control", "Melodía", "Perdón", "Alegría", "ES", "EL", "GOBIERNO", "DE", "LA", "IA"]
    margin_ratio: float = 0.1

    bg = Image.open(plantilla).convert("RGBA")

    W, H = bg.size
    start_index: int = 255

    # zonas máximas para el texto
    max_w = W * (1 - 2 * margin_ratio)
    max_h = H * (1 - 2 * margin_ratio)

    start = time.perf_counter()
    logger.info(f"Generando imágenes de texto ({len(palabras)} palabras) para terminal '{terminal}'")
    for i, word in enumerate(palabras):
        logger.info(f"[TEXTO {i+1}/{len(palabras)}] {word}")
        # arrancamos con un tamaño de fuente grande y bajamos hasta que quepa usando textbbox
        font_size = int(min(max_w, max_h))  # punto de partida
        font = None
        while True:
            font = ImageFont.truetype(font_path, font_size)
            draw_measure = ImageDraw.Draw(bg)
            bbox = draw_measure.textbbox((0, 0), word, font=font)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            if (w <= max_w and h <= max_h) or font_size <= 1:
                break
            font_size -= 2

        # creamos la imagen final
        canvas = bg.copy().convert("RGBA")
        # calcula ancho de contorno para efecto neon
        stroke_width = 20
        # recalcula bounding box con contorno para centrar correctamente
        measurer = ImageDraw.Draw(canvas)
        bbox = measurer.textbbox((0, 0), word, font=font, stroke_width=stroke_width)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = (W - w) // 2 - bbox[0]
        y = (H - h) // 2 - bbox[1]
        # capa de glow: dibuja texto con contorno y aplica blur
        glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw_glow = ImageDraw.Draw(glow_layer)
        draw_glow.text((x, y), word, font=font, fill="white", stroke_width=stroke_width, stroke_fill="white")
        glow_blur = glow_layer.filter(ImageFilter.GaussianBlur(radius=8))
        # reduce glow opacity a 50%
        alpha = glow_blur.getchannel('A').point(lambda a: a * 0.5)
        glow_blur.putalpha(alpha)
        # compone el glow tras el fondo
        canvas = Image.alpha_composite(canvas, glow_blur)
        # dibuja el texto principal sobre el glow
        draw = ImageDraw.Draw(canvas)
        draw.text((x, y), word, font=font, fill="white")


        index = start_index - i
        filename = f"{index:03d}.png"
        out_path = Path(origin_folder) / filename
        canvas.save(out_path)
    elapsed = time.perf_counter() - start
    logger.info(f"Generación de imágenes con texto completada en {elapsed:.2f}s")
    return {"fase":"texto","palabras":len(palabras),"elapsed":elapsed}


def convierte_imagenes(terminal, width = 800, height = 480, bpp=16, invert=False):
    terminal = terminal.lower()
    if terminal not in DATOS:
        raise ValueError(f"Terminal '{terminal}' no encontrado en DATOS")
        
    origin_folder = "/home/angel/lgptclient/images"
    destiny_folder = f"/home/angel/lgptclient/images{terminal}"
    
    Path(destiny_folder).mkdir(parents=True, exist_ok=True)
    empty_folder(destiny_folder)
    Path(destiny_folder).mkdir(parents=True, exist_ok=True)
        
    total_files = sum(1 for i in range(1, 1000) if Path(origin_folder, f"{i:03d}.png").exists())
    start = time.perf_counter()
    logger.info(f"Convirtiendo {total_files} imágenes para '{terminal}' (invert={invert})")

    processed = 0
    errors = 0

    for i in range(1, 1000):
        png_file = Path(origin_folder) / f"{i:03d}.png"
        if not png_file.exists():
            continue
        code_hex = note_from_index(i)
        bin_file = Path(destiny_folder) / f"imagenes/{i:03d}.bin"
        pngd_file = Path(destiny_folder) / f"imagenes/imagenes_pi/{code_hex}.png"
        try:
            logger.info(f"[IMG {processed+1}/{total_files}] {png_file.name} -> {code_hex}")
            img = Image.open(png_file)
            if invert:
                logger.info("  Invertida")
                img = img.transpose(Image.FLIP_TOP_BOTTOM).transpose(Image.FLIP_LEFT_RIGHT)
            pngd_file.parent.mkdir(parents=True, exist_ok=True)
            img.save(pngd_file)
            png_to_bin(pngd_file, bin_file, width, height, bpp)
            resize_png(pngd_file, pngd_file)
            processed += 1
            if processed % 25 == 0 or processed == total_files:
                logger.info(f"Procesadas {processed}/{total_files} imágenes")
        except Exception as e:
            errors += 1
            logger.error(f"Error procesando {png_file.name}: {e}")

    elapsed = time.perf_counter() - start
    logger.info(f"Conversión terminada en {elapsed:.2f}s. OK={processed} Errores={errors} ({processed/elapsed if elapsed else 0:.1f} img/s)")
    return {"fase":"imagenes","ok":processed,"errores":errors,"elapsed":elapsed}
                

def convierte_animaciones(terminal, width = 800, height = 480, bpp=16, invert=False):
    terminal = terminal.lower()
    if terminal not in DATOS:
        raise ValueError(f"Terminal '{terminal}' no encontrado en DATOS")
        
    origin_folder = "/home/angel/lgptclient/animated-png"
    destiny_folder = f"/home/angel/lgptclient/images{terminal}/animaciones"
    
    Path(destiny_folder).mkdir(parents=True, exist_ok=True)
        
    
    start = time.perf_counter()
    processed = 0
    anim_count = 0
    logger.info(f"Convirtiendo animaciones para '{terminal}'")
    for animation_dir in Path(origin_folder).iterdir():
        if not animation_dir.is_dir():
            continue
        animation_name = animation_dir.name
        frames = sorted(animation_dir.glob("*.png"))
        if not frames:
            continue
        anim_count += 1
        logger.info(f"Animación '{animation_name}' ({len(frames)} frames)")
        for png_file in frames:
            try:
                logger.info(f"[ANIM {animation_name}] Frame {png_file.name}")
                img = Image.open(png_file)
                if invert:                    
                    img = img.transpose(Image.FLIP_TOP_BOTTOM).transpose(Image.FLIP_LEFT_RIGHT)
                try:
                    frame_str = png_file.stem.split('_')[-1]
                    frame_number = int(frame_str)
                except (ValueError, IndexError):
                    frame_number = processed  # fallback
                pngd_file = Path(destiny_folder) / f"imagenes_pi/{animation_name}_{frame_number:03d}.png"
                bin_file = Path(destiny_folder) / f"{animation_name}_{frame_number:03d}.bin"
                pngd_file.parent.mkdir(parents=True, exist_ok=True)
                img.save(pngd_file)
                png_to_bin(pngd_file, bin_file, width, height, bpp)
                resize_png(pngd_file, pngd_file)
                processed += 1
                if processed % 50 == 0:
                    logger.info(f"Frames procesados: {processed}")
            except Exception as e:
                logger.error(f"Error en animación {animation_name}, frame {png_file.name}: {e}")
    elapsed = time.perf_counter() - start
    logger.info(f"Animaciones convertidas: {anim_count} | Frames totales: {processed} en {elapsed:.2f}s ({processed/elapsed if elapsed else 0:.1f} fps)")
    return {"fase":"animaciones","animaciones":anim_count,"frames":processed,"elapsed":elapsed}

def generar_markdown_imagenes(terminal, columnas=5, thumb_width=600):
    """Genera /home/angel/lgptclient/Imagenes.md mostrando miniaturas.

    Origen fijo: /home/angel/lgptclient/images
    Destino fijo: /home/angel/lgptclient/Imagenes.md
    Se buscan archivos nombrados con su código hexadecimal (01..FF). Si no existe
    ese nombre en hex, se intenta la variante decimal de 3 dígitos (001..255) para
    mantener compatibilidad con el flujo actual. Solo se listan los que existan.
    """
    terminal = terminal.lower()
    base_dir = Path("/home/angel/lgptclient")
    imagenes_dir = base_dir / "images"
    markdown_path = base_dir / "Imagenes.md"

    if not imagenes_dir.exists():
        logger.warning(f"Directorio de imágenes no existe: {imagenes_dir}")
        return {"fase":"markdown","imagenes":0,"elapsed":0.0}

    items = []
    for i in range(1, 256):  # 0x01..0xFF
        code_hex = note_from_index(i)  # 01..FF
        # Preferimos nombre hex (01.png..FF.png)
        png_path = imagenes_dir / f"{code_hex}.png"
        if not png_path.exists():
            # fallback a decimal 3 dígitos (001.png..255.png)
            png_dec = imagenes_dir / f"{i:03d}.png"
            if png_dec.exists():
                png_path = png_dec
            else:
                continue
        # ruta relativa para el markdown (desde root del repo)
        try:
            rel_path = png_path.relative_to(base_dir)
        except ValueError:
            rel_path = png_path  # por si acaso
        items.append((code_hex, rel_path.as_posix()))

    if not items:
        logger.warning("No se encontraron imágenes para generar el markdown.")
        return {"fase":"markdown","imagenes":0,"elapsed":0.0}
    start = time.perf_counter()
    logger.info(f"Generando markdown con {len(items)} imágenes")

    filas = []
    for idx in range(0, len(items), columnas):
        fila_items = items[idx:idx+columnas]
        celdas = []
        for code, rel in fila_items:
            celdas.append(
                f'<td align="center" style="font-size: 20px; padding:4px; font-family:monospace;">{code}<br><img src="{rel}" width="{thumb_width}" /></td>'
            )
        while len(celdas) < columnas:
            celdas.append('<td></td>')
        filas.append(f"<tr>{''.join(celdas)}</tr>")

    contenido = [
        "# Galería de Imágenes", "",
        f"Terminal (última generación): {terminal}", "",
        "Cada celda muestra el código hexadecimal y su miniatura desde images/.", "",
        "<table>", *filas, "</table>", "",
        "Generado automáticamente por genera.py"
    ]
    markdown_path.write_text("\n".join(contenido), encoding="utf-8")
    elapsed = time.perf_counter() - start
    logger.info(f"Markdown generado: {markdown_path} en {elapsed:.2f}s")
    return {"fase":"markdown","imagenes":len(items),"elapsed":elapsed}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog='Actualiza')
    parser.add_argument('prima', type=str, help='Primer argumento')
    parser.add_argument('--debug', action='store_true', help='(Opcional) activa nivel DEBUG adicional')
    args = parser.parse_args()
    if not args.prima:
        parser.error("First argument cannot be empty")
    
    
    if args.debug:
        logger.setLevel(DEBUG)
        logger.debug("Modo DEBUG activado (pero ya se muestran items en INFO)")
    logger.info(f"Iniciando generación para terminal '{args.prima}'")
    t0 = time.perf_counter()
    fases = []
    # 1) Primero compone las imágenes presentes en images/png sobre el fondo
    fases.append(genera_imagenes_desde_subpng())
    # 2) Luego genera las imágenes de texto (que podrían sobrescribir números altos)
    fases.append(genera_imagenes_con_texto(args.prima))
    fases.append(convierte_imagenes(args.prima, invert=DATOS[args.prima]["invert"]))
    fases.append(convierte_animaciones(args.prima, invert=DATOS[args.prima]["invert"]))
    fases.append(generar_markdown_imagenes(args.prima))
    total_elapsed = time.perf_counter() - t0
    logger.info("Resumen de tiempos:")
    for f in fases:
        if not f:  # por seguridad
            continue
        if f["fase"] == "texto":
            logger.info(f"  Texto: {f['palabras']} palabras en {f['elapsed']:.2f}s ({f['palabras']/f['elapsed'] if f['elapsed'] else 0:.1f} img/s)")
        elif f["fase"] == "imagenes":
            logger.info(f"  Imágenes: {f['ok']} OK, {f['errores']} err en {f['elapsed']:.2f}s ({f['ok']/f['elapsed'] if f['elapsed'] else 0:.1f} img/s)")
        elif f["fase"] == "animaciones":
            logger.info(f"  Animaciones: {f['animaciones']} anim / {f['frames']} frames en {f['elapsed']:.2f}s ({f['frames']/f['elapsed'] if f['elapsed'] else 0:.1f} fps)")
        elif f["fase"] == "markdown":
            logger.info(f"  Markdown: {f['imagenes']} miniaturas en {f['elapsed']:.2f}s")
    logger.info(f"Total: {total_elapsed:.2f}s")
    logger.info("Proceso completo finalizado.")
