import time
import pysftp
from urllib.parse import urlparse
import paramiko
from genera_imagenes import convert_all_png_to_bin,generar_markdown_imagenes
from ftpcliente import SftpCliente



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

def actualiza_sombrilla(generate_images=False, upload_images=False, restart_service=False, pip=False):    
    if generate_images:
        print("Generamos imágenes 800 480")
        convert_all_png_to_bin("/home/angel/lgptclient/images/", "/home/angel/lgptclient/imagessombrilla/", 800, 480, invert=True)
    IP_SOMBRILLA = "192.168.0.4"        
    sftp = SftpCliente(IP_SOMBRILLA, "sombrilla")
    sftp.connect()    
    sftp.update_sources()
    if upload_images:        
        sftp.upload_images()
    
    if pip:
        sftp.update_pyton()

    if restart_service:
        sftp.ejecuta('sudo systemctl restart cliente')
        time.sleep(2)
        status = sftp.ejecuta('sudo systemctl status cliente')
        output=''
        for line in status:
            output=output+line
    
    
    if restart_service:
        print(output)
