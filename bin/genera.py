import argparse
from pathlib import Path
import shutil
import struct
from PIL import Image, ImageDraw, ImageFont, ImageFilter

DATOS = {
    "sombrilla":{
        "invert": True
    },
        "maleta":{
        "invert": False
    }
}

ANIMATED_PNG_OUTPUT_FOLDER = "/home/angel/lgptclient/images/imagenes_pi"

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
    with open(bin_path, "wb") as f:
        f.write(img_data)

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

def empty_folder(folder_path):
    """
    Delete all files in a folder without deleting the folder itself.
    
    :param folder_path: Path to the folder to be emptied.
    """
    folder = Path(folder_path)
    if folder.exists() and folder.is_dir():
        # Iterate and remove all files in the folder
        for file in folder.iterdir():
            if file.is_file():
                file.unlink()  # Remove file
            elif file.is_dir():
                shutil.rmtree(file)  # Remove subdirectories

def genera_imagenes_con_texto(terminal):
    terminal = terminal.lower()
    if terminal not in DATOS:
        raise ValueError(f"Terminal '{terminal}' no encontrado en DATOS")
        
    origin_folder = "/home/angel/lgptclient/images"  
    plantilla = "/home/angel/lgptclient/images/fondo.png"  
    font_path="/home/angel/lgptclient/images/NeonSans.ttf"
    palabras = ["We're", "charging", "our", "battery", "And now", "we're", "full of", "energy", "WE", "ARE", "THE", "ROBOTS"]
    margin_ratio: float = 0.1

    bg = Image.open(plantilla).convert("RGBA")

    W, H = bg.size
    start_index: int = 999

    # zonas máximas para el texto
    max_w = W * (1 - 2 * margin_ratio)
    max_h = H * (1 - 2 * margin_ratio)

    for i, word in enumerate(palabras):
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
        canvas.save(Path(origin_folder) / filename)


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
    
    processed = 0
    errors = 0
    
    for i in range(1, 1000):
        png_file = Path(origin_folder) / f"{i:03d}.png"
        bin_file = Path(destiny_folder) / f"imagenes/{i:03d}.bin"
        pngd_file = Path(destiny_folder) / f"imagenes/imagenes_pi/{note_from_index(i)}.png"
        
        if png_file.exists():
            img = Image.open(png_file)
            
            if invert:
                img = img.transpose(Image.FLIP_TOP_BOTTOM)
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
            
            # Ensure the directory exists
            pngd_file.parent.mkdir(parents=True, exist_ok=True)
            
            # ... rest of your conversion code ...
            img.save(pngd_file)
            png_to_bin(pngd_file, bin_file, width, height, bpp)
            resize_png(pngd_file, pngd_file)
            processed += 1
                

def convierte_animaciones(terminal, width = 800, height = 480, bpp=16, invert=False):
    terminal = terminal.lower()
    if terminal not in DATOS:
        raise ValueError(f"Terminal '{terminal}' no encontrado en DATOS")
        
    origin_folder = "/home/angel/lgptclient/animated-png"
    destiny_folder = f"/home/angel/lgptclient/images{terminal}/animaciones"
    
    Path(destiny_folder).mkdir(parents=True, exist_ok=True)
        
    
    processed = 0
    
    for animation_dir in Path(origin_folder).iterdir():
        if animation_dir.is_dir():
            animation_name = animation_dir.name
            for png_file in sorted(animation_dir.glob("*.png")):
                img = Image.open(png_file)
                
                if invert:
                    img = img.transpose(Image.FLIP_TOP_BOTTOM)
                    img = img.transpose(Image.FLIP_LEFT_RIGHT)
                
                # Extract frame number from filename
                try:
                    frame_str = png_file.stem.split('_')[-1]  # Get last part after underscore
                    frame_number = int(frame_str)
                except (ValueError, IndexError):
                    # If extraction fails, keep using sequential numbering
                    pass
                pngd_file = Path(destiny_folder) / f"imagenes_pi/{animation_name}_{frame_number:03d}.png"
                bin_file = Path(destiny_folder) / f"{animation_name}_{frame_number:03d}.bin"
                
                pngd_file.parent.mkdir(parents=True, exist_ok=True)
                
                img.save(pngd_file)
                png_to_bin(pngd_file, bin_file, width, height, bpp)
                resize_png(pngd_file, pngd_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog='Actualiza')
    parser.add_argument('prima', type=str, help='Primer argumento')
    args = parser.parse_args()
    if not args.prima:
        parser.error("First argument cannot be empty")
    
    
    genera_imagenes_con_texto(args.prima)

    #convierte_imagenes(args.prima, invert=DATOS[args.prima]["invert"])
    #convierte_animaciones(args.prima, invert=DATOS[args.prima]["invert"])
