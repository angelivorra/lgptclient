import time
import pysftp
from urllib.parse import urlparse
import paramiko
from genera_imagenes import convert_all_png_to_bin,generar_markdown_imagenes
from ftpcliente import SftpCliente


GENERATE_IMAGES = False
UPLOAD_IMAGES = False
RESTART_SERVICE = False


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

def actualiza_sombrilla(pip=False):
        
    print("Generamos imágenes 800 480")
    if GENERATE_IMAGES:
        convert_all_png_to_bin("/home/angel/lgptclient/images/", "/home/angel/lgptclient/imagessombrilla/", 800, 480, invert=True)
    IP_SOMBRILLA = "192.168.0.4"        
    sftp = SftpCliente(IP_SOMBRILLA, "sombrilla")
    sftp.connect()
    sftp.update_sources()
    if UPLOAD_IMAGES:
        sftp.upload_images()
    
    if pip:
        sftp.update_pyton()

    if RESTART_SERVICE:
        sftp.ejecuta('sudo systemctl restart cliente')
        time.sleep(2)
        status = sftp.ejecuta('sudo systemctl status cliente')
        output=''
        for line in status:
            output=output+line
    
    sftp.disconnect()
    if RESTART_SERVICE:
        print(output)
