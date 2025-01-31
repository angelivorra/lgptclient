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
    Convert all PNG files (001.png to 999.png) in the origin folder to raw binary format and save to the destiny folder.
    
    :param origin_folder: Path to the folder containing PNG images.
    :param destiny_folder: Path to the folder to save the raw binary files.
    :param width: Width of the screen in pixels (for resizing).
    :param height: Height of the screen in pixels (for resizing).
    :param bpp: Bits per pixel (default is 16 for RGB565, can be 24 for RGB or 32 for RGBA).
    :param invert: Boolean flag to invert the image vertically (default is False).
    """
    # Ensure destiny folder exists
    
    
    # Empty the destiny folder before processing
    empty_folder(destiny_folder)
    Path(destiny_folder).mkdir(parents=True, exist_ok=True)
    empty_folder(ANIMATED_PNG_OUTPUT_FOLDER)
    Path(ANIMATED_PNG_OUTPUT_FOLDER).mkdir(parents=True, exist_ok=True)
    #for i in range(1, 1000):
    for i in range(1, 3):
        png_file = Path(origin_folder) / f"{i:03d}.png"
        bin_file = Path(destiny_folder) / f"{i:03d}.bin"
        pngd_file = Path(destiny_folder) / f"imagenes_pi/{i:05d}.{note_from_index(i)}.png"
        
        if png_file.exists():
            img = Image.open(png_file)
            
            if invert:
                img = img.transpose(Image.FLIP_TOP_BOTTOM)
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
            
            # Ensure the directory for the processed image exists
            pngd_file.parent.mkdir(parents=True, exist_ok=True)
            
            img.save(pngd_file)
            print(f"Processing {png_file}...")
            png_to_bin(pngd_file, bin_file, width, height, bpp)
            resize_png(pngd_file, pngd_file)
            print(f"Saved {pngd_file}")
        else:
            pass
        
        
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
    
    
    # for mp4_file in Path("/home/angel/lgptclient/animated-png").glob("*.svg"):
    #     print(f"Processing animated MP4: {mp4_file}")
    #     try:
    #         tree = ET.parse(mp4_file)
    #         root = tree.getroot()

    #         frames = root.findall(".//{http://www.w3.org/2000/svg}animate")
    #         if not frames:
    #             frames = root.findall(".//{http://www.w3.org/2000/svg}set")

    #         for i, frame in enumerate(frames):
    #             # Convert the frame to RGB
    #             png_bytes = cairosvg.svg2png()
                
    #             # Convertir los bytes a una imagen de Pillow
    #             current_frame = Image.open(BytesIO(png_bytes))

    #             # Crear una nueva imagen con fondo negro
    #             new_img = Image.new("RGBA", current_frame.size, (0, 0, 0, 255))  # Fondo negro

    #             # Pegar el frame en el centro de la nueva imagen
    #             new_img.paste(current_frame, (0, 0), current_frame)

    #             # Invertir la imagen si es necesario
    #             if invert:
    #                 new_img = new_img.transpose(Image.FLIP_TOP_BOTTOM)
    #                 new_img = new_img.transpose(Image.FLIP_LEFT_RIGHT)
                    
    #             base_name = mp4_file.stem
    #             pngd_file = Path(ANIMATED_PNG_OUTPUT_FOLDER) / f"imagenes_pi/{base_name}_{i:03d}.png"
                    
    #             pngd_file.parent.mkdir(parents=True, exist_ok=True)
                
    #             # Generate output filename for this frame
    #             bin_file = Path(ANIMATED_PNG_OUTPUT_FOLDER) / f"{base_name}_{i:03d}.bin"
    #             current_frame.save(pngd_file)
    #             png_to_bin(pngd_file, bin_file, width, height, bpp)
    #             resize_png(pngd_file, pngd_file)
    #             print(f"Saved frame {i} to {pngd_file}")

    #     except Exception as e:
    #         print(f"Error processing {mp4_file}: {str(e)}")


    for webp_file in Path("/home/angel/lgptclient/animated-png").glob("*.webm"):
        print(f"Processing animated WebP: {webp_file}")
        try:
            with Image.open(webp_file) as img:
                # Verificar si el WebP es animado
                if not img.is_animated:
                    print(f"{webp_file} is not an animated WebP.")
                    continue

                # Iterar sobre cada frame del WebP animado
                for i in range(img.n_frames):
                    img.seek(i)
                    current_frame = img.copy()

                    # Crear una nueva imagen con fondo negro
                    new_img = Image.new("RGBA", current_frame.size, (0, 0, 0, 255))  # Fondo negro

                    # Pegar el frame en el centro de la nueva imagen
                    new_img.paste(current_frame, (0, 0), current_frame)

                    # Invertir la imagen si es necesario
                    if invert:
                        new_img = new_img.transpose(Image.FLIP_TOP_BOTTOM)
                        new_img = new_img.transpose(Image.FLIP_LEFT_RIGHT)

                    base_name = webp_file.stem
                    pngd_file = Path(ANIMATED_PNG_OUTPUT_FOLDER) / f"imagenes_pi/{base_name}_{i:03d}.png"

                    pngd_file.parent.mkdir(parents=True, exist_ok=True)

                    # Generar el nombre del archivo de salida para este frame
                    bin_file = Path(ANIMATED_PNG_OUTPUT_FOLDER) / f"{base_name}_{i:03d}.bin"
                    new_img.save(pngd_file)
                    png_to_bin(pngd_file, bin_file, width, height, bpp)
                    resize_png(pngd_file, pngd_file)
                    print(f"Saved frame {i} to {pngd_file}")

        except Exception as e:
            print(f"Error processing {webp_file}: {str(e)}")