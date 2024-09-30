from pathlib import Path
from PIL import Image
import struct
import shutil

def png_to_bin(png_path, bin_path, screenx, screeny, bpp=24):
    """
    Convert a PNG image to raw binary format for framebuffer.

    :param png_path: Path to the PNG image.
    :param bin_path: Path to save the raw binary image.
    :param screenx: Width of the screen in pixels.
    :param screeny: Height of the screen in pixels.
    :param bpp: Bits per pixel (e.g., 16 for RGB565, 24 for RGB, 32 for RGBA).
    """
    # Open the PNG image using Pillow
    img = Image.open(png_path)
    
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

def convert_all_png_to_bin(origin_folder, destiny_folder, width, height, bpp=16):
    """
    Convert all PNG files (001.png to 999.png) in the origin folder to raw binary format and save to the destiny folder.
    
    :param origin_folder: Path to the folder containing PNG images.
    :param destiny_folder: Path to the folder to save the raw binary files.
    :param width: Width of the screen in pixels (for resizing).
    :param height: Height of the screen in pixels (for resizing).
    :param bpp: Bits per pixel (default is 16 for RGB565, can be 24 for RGB or 32 for RGBA).
    """
    # Ensure destiny folder exists
    Path(destiny_folder).mkdir(parents=True, exist_ok=True)
    
    # Empty the destiny folder before processing
    empty_folder(destiny_folder)
    
    for i in range(1, 1000):
        png_file = Path(origin_folder) / f"{i:03d}.png"
        bin_file = Path(destiny_folder) / f"{i:03d}.bin"
        
        if png_file.exists():
            print(f"Processing {png_file}...")
            png_to_bin(png_file, bin_file, width, height, bpp)
            print(f"Saved {bin_file}")
        else:
            print(f"File {png_file} not found, skipping...")

if __name__ == "__main__":
    convert_all_png_to_bin("/home/angel/lgptclient/images/", "/home/angel/lgptclient/images800480/", 800, 480, 16)
