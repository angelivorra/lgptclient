from io import BytesIO
import os
from pathlib import Path
from PIL import Image, ImageSequence
import struct
import shutil

import urllib
import cairosvg
from xml.etree import ElementTree as ET

ANIMATED_PNG_OUTPUT_FOLDER = "/home/angel/lgptclient/animaciones"

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


def generar_markdown_imagenes(folder):
    archivos_png = sorted([
        f for f in os.listdir(folder) 
        if f.lower().endswith('.png')
    ])
    lines = []
    for filename in archivos_png:
        parts = filename.split('.')
        # parts: ["00001","menos2","C","png"]
        if len(parts) >= 3 and parts[1].startswith("menos"):
            num_str = parts[1].replace("menos","-")
            title = parts[2] + num_str
            encoded_filename = urllib.parse.quote(filename)
            lines.append(f"![{title}](images800480/imagenes_pi/{encoded_filename})\n")
    return ''.join(lines) 

def convert_all_png_to_bin(origin_folder, destiny_folder, width, height, bpp=16, invert=False):
    """
    Convert all PNG files (001.png to 999.png) in the origin folder to raw binary format.
    """
    print("\n=== Image Conversion Process Started ===")
    
    # Ensure destiny folder exists
    Path(destiny_folder).mkdir(parents=True, exist_ok=True)
    Path(ANIMATED_PNG_OUTPUT_FOLDER).mkdir(parents=True, exist_ok=True)
    
    # Empty the destination folders
    print("Cleaning destination folders...")
    empty_folder(destiny_folder)
    empty_folder(ANIMATED_PNG_OUTPUT_FOLDER)
    
    total_files = sum(1 for i in range(1, 1000) if Path(origin_folder, f"{i:03d}.png").exists())
    print(f"\nFound {total_files} PNG files to process")
    print("\nStarting conversion...")
    
    processed = 0
    errors = 0
    
    #for i in range(1, 1000):
    for i in range(1, 1000):
        png_file = Path(origin_folder) / f"{i:03d}.png"
        bin_file = Path(destiny_folder) / f"{i:03d}.bin"
        pngd_file = Path(destiny_folder) / f"imagenes_pi/{i:05d}.{note_from_index(i)}.png"
        
        if png_file.exists():
            try:
                print(f"\nProcessing [{i:03d}/{total_files}]: {png_file.name}")
                img = Image.open(png_file)
                
                if invert:
                    print("  - Applying image inversion")
                    img = img.transpose(Image.FLIP_TOP_BOTTOM)
                    img = img.transpose(Image.FLIP_LEFT_RIGHT)
                
                # Ensure the directory exists
                pngd_file.parent.mkdir(parents=True, exist_ok=True)
                
                print(f"  - Converting to {width}x{height} @ {bpp}bpp")
                # ... rest of your conversion code ...
                img.save(pngd_file)
                print(f"Processing {png_file}...")
                png_to_bin(pngd_file, bin_file, width, height, bpp)
                resize_png(pngd_file, pngd_file)
                print(f"Saved {pngd_file}")
                processed += 1
                print(f"  ✓ Saved: {bin_file.name}")
                
            except Exception as e:
                errors += 1
                print(f"  ✗ Error processing {png_file.name}: {str(e)}")
    
    print(f"\n=== Conversion Complete ===")
    print(f"Total processed: {processed}")
    print(f"Successful: {processed - errors}")
    print(f"Errors: {errors}")

    for animation_dir in Path("/home/angel/lgptclient/animated-png").iterdir():
        if animation_dir.is_dir():
            animation_name = animation_dir.name
            print(f"Processing animation: {animation_name}")
            for png_file in sorted(animation_dir.glob("*.png")):
                try:
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
                    pngd_file = Path(ANIMATED_PNG_OUTPUT_FOLDER) / f"imagenes_pi/{animation_name}_{frame_number:03d}.png"
                    bin_file = Path(ANIMATED_PNG_OUTPUT_FOLDER) / f"{animation_name}_{frame_number:03d}.bin"
                    
                    pngd_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    img.save(pngd_file)
                    png_to_bin(pngd_file, bin_file, width, height, bpp)
                    resize_png(pngd_file, pngd_file)
                    print(f"Saved frame {frame_number} to {pngd_file}")
                except Exception as e:
                    print(f"Error processing {png_file}: {str(e)}")
