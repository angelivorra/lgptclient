import argparse
import time
import pysftp
from urllib.parse import urlparse
import paramiko
from genera_imagenes import convert_all_png_to_bin, generar_markdown_imagenes
from ftpcliente import SftpCliente

parser = argparse.ArgumentParser(prog='Actualiza')
parser.add_argument('--pip', default=False)
args = parser.parse_args()



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

def actualiza_maleta():
        
    print("Generamos imágenes 800 480")
    convert_all_png_to_bin("/home/angel/lgptclient/images/", "/home/angel/lgptclient/images800480/", 800, 480)
    
    IP_MALETA = "192.168.0.3"    
    sftp = SftpCliente(IP_MALETA, "maleta")
    sftp.connect()
    sftp.update_sources()
    sftp.upload_images()
    
    # if args.pip:
    #     sftp.update_pyton()

    sftp.ejecuta('sudo systemctl restart cliente')
    time.sleep(2)
    status = sftp.ejecuta('sudo systemctl status cliente')
    output=''
    for line in status:
        output=output+line
    
    sftp.disconnect()
    print(output)
