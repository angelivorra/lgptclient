import argparse
from pathlib import Path
import shutil
import struct
from PIL import Image

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
    Convierte un índice numérico a una nota musical con octava.
    
    :param index: Índice del archivo (001-999).
    :return: Nombre de la nota correspondiente en formato CDEFGAB y octava.
    """
    # Definir las notas musicales en formato CDEFGAB con sostenidos
    notas = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    
    # Calcular la posición de la nota en la lista
    base_index = (index - 1) % 12
    
    # Calcular la octava correspondiente
    octava = (index - 1) // 12 - 2  # Empieza en menos2 para ajustar las octavas
    
    # Convertir la octava negativa al formato "menosX"
    if octava < 0:
        octava_str = f"menos{abs(octava)}"
    else:
        octava_str = str(octava)
    
    # Determinar la nota
    nota = notas[base_index]
    
    # Formar el nombre con la octava
    return f"{octava_str}.{nota}"


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
        pngd_file = Path(destiny_folder) / f"imagenes/imagenes_pi/{i:05d}.{note_from_index(i)}.png"
        
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
    
    convierte_imagenes(args.prima, invert=DATOS[args.prima]["invert"])
    convierte_animaciones(args.prima, invert=DATOS[args.prima]["invert"])
    