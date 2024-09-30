#10.42.0.73
import argparse
import time
import pysftp
from urllib.parse import urlparse
import os
import paramiko
from PIL import Image

parser = argparse.ArgumentParser(prog='Actualiza')
parser.add_argument('--pip', default=False)
args = parser.parse_args()
IP_MALETA = "192.168.0.3"


from PIL import Image

def png_to_bin(png_path, bin_path, screenx, screeny, bpp=24):
    """
    Convert a PNG image to raw binary format for framebuffer.

    :param png_path: Path to the PNG image.
    :param bin_path: Path to save the raw binary image.
    :param screenx: Width of the screen in pixels.
    :param screeny: Height of the screen in pixels.
    :param bpp: Bits per pixel (e.g., 24 for RGB, 32 for ARGB).
    """
    # Open the PNG image using Pillow
    img = Image.open(png_path)
    
    # Ensure the image matches the screen size (resize if necessary)
    img = img.resize((screenx, screeny))
    
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

class SftpMaleta:
    def __init__(self):
        self.connection = None
        self.hostname = IP_MALETA
        self.username = "angel"
        self.port = 22

    def connect(self):
        """Connects to the sftp server and returns the sftp connection object"""

        try:
            # Get the sftp connection object
            self.connection = pysftp.Connection(
                host=self.hostname,
                username=self.username,
                port=self.port,
                #private_key='/home/angel/.ssh/id_rsa'
            )
        except Exception as err:
            raise Exception(err)
        finally:
            print(f"Connected to {self.hostname} as {self.username}.")

    def disconnect(self):
        """Closes the sftp connection"""
        self.connection.close()
        print(f"Disconnected from host {self.hostname}")

    def upload(self):
        """
        Uploads the source files from local to the sftp server.
        """

        try:

            # Download file from SFTP
            self.connection.put("/home/angel/lgptclient/bin/cliente/main_server.py", "/home/angel/bin/main_server.py")
            self.connection.put("/home/angel/lgptclient/bin/cliente/image_events.py", "/home/angel/bin/image_events.py")
            self.connection.put("/home/angel/lgptclient/bin/cliente/gpio_events.py", "/home/angel/bin/gpio_events.py")            
            self.connection.put("/home/angel/lgptclient/bin/cliente.maleta.json", "/home/angel/config.json")
            self.connection.put("/home/angel/lgptclient/requirements_maleta.txt", "/home/angel/requirements.txt")
            print("Maleta updated")

        except Exception as err:
            raise Exception(err)


def ejecuta(ssh, comando):
    print(f"Ejecutamos Comando {comando}")
    stdin, stdout, stderr = ssh.exec_command(comando)
    exit_status = stdout.channel.recv_exit_status()
    if exit_status == 0:
        print("Hecho")
        return stdout.readlines()
    else:
        print(f"Error {exit_status}")
        print(f"Errores {stderr.readlines()}")
        return False
    

if __name__ == "__main__":
    
    sftp = SftpMaleta()

    genera_imagenes

    # Connect to SFTP
    sftp.connect()
    sftp.upload()
    sftp.disconnect()
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(IP_MALETA)
    if args.pip:        
        ejecuta(ssh, 'python -m pip cache purge')        
        ejecuta(ssh, 'rm -r /home/angel/venv')        
        ejecuta(ssh, 'python3 -m venv /home/angel/venv')
        ejecuta(ssh, '/home/angel/venv/bin/pip3 install --upgrade pip')
        ejecuta(ssh, '/home/angel/venv/bin/pip3 install -r /home/angel/requirements.txt')                
        
    ejecuta(ssh, 'rm /home/angel/midi_notes_log.csv')
    ejecuta(ssh, 'sudo systemctl restart cliente')
    time.sleep(2)
    status = ejecuta(ssh, 'sudo systemctl status cliente')
    output=''
    for line in status:
        output=output+line
    print(output)
    ssh.close()