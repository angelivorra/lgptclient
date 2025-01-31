

from pathlib import Path
import paramiko
import pysftp


REMOTE_FOLDER  = "/home/angel/images/"
ANIM_REMOTE_FOLDER = "/home/angel/animaciones/"

class SftpCliente:
    def __init__(self, ip, cliente):
        self.connection = None
        self.hostname = ip
        self.username = "angel"
        self.port = 22
        self.cliente = cliente
        self.ssh = None

    def connect(self):
        """Connects to the sftp server and returns the sftp connection object"""

        try:
            # Get the sftp connection object
            self.connection = pysftp.Connection(
                host=self.hostname,
                username=self.username,
                port=self.port,                
            )
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh.connect(self.hostname)
        except Exception as err:
            raise Exception(err)
        finally:
            print(f"Connected to {self.hostname} as {self.username}.")

    def ejecuta(self, comando):
        #print(f"Ejecutamos Comando {comando}")
        stdin, stdout, stderr = self.ssh.exec_command(comando)
        exit_status = stdout.channel.recv_exit_status()
        if exit_status == 0:
            #print("Hecho")
            return stdout.readlines()
        else:
            print(f"Error {exit_status}")
            print(f"Errores {stderr.readlines()}")
            return False

    def update_pyton(self):
        print("Actualizamos python")
        self.ejecuta('python3 -m pip cache purge')
        self.ejecuta('rm -r /home/angel/venv')
        self.ejecuta('python3 -m venv /home/angel/venv')
        self.ejecuta('/home/angel/venv/bin/pip3 install --upgrade pip')
        self.ejecuta('/home/angel/venv/bin/pip3 install -r /home/angel/requirements.txt')

    def disconnect(self):
        """Closes the sftp connection"""
        self.connection.close()
        print(f"Disconnected from host {self.hostname}")

    def update_sources(self): 
        print("Actualizamos fuentes")    
        self.connection.put("/home/angel/lgptclient/bin/cliente/main_server.py", "/home/angel/bin/main_server.py")
        self.connection.put("/home/angel/lgptclient/bin/cliente/image_events.py", "/home/angel/bin/image_events.py")
        self.connection.put("/home/angel/lgptclient/bin/cliente/gpio_events.py", "/home/angel/bin/gpio_events.py")        
        self.connection.put(f"/home/angel/lgptclient/bin/cliente.{self.cliente}.json", "/home/angel/config.json")
        self.connection.put(f"/home/angel/lgptclient/requirements_{self.cliente}.txt", "/home/angel/requirements.txt")

    def upload_images(self):
        IMG_FOLDER = Path(f"/home/angel/lgptclient/images{self.cliente}")
        ANIMACIONES_FOLDER = Path(f"/home/angel/lgptclient/animaciones")
        print(f"Uploading images")
        # Upload all .bin files from /home/angel/images800480/ to /home/angel/images/            
        for bin_file in IMG_FOLDER.glob("*.bin"):
            print(f"Uploading {bin_file} to {REMOTE_FOLDER}")
            self.connection.put(bin_file, REMOTE_FOLDER + bin_file.name)
        for bin_file in ANIMACIONES_FOLDER.glob("*.bin"):
            print(f"Uploading {bin_file} to {ANIM_REMOTE_FOLDER}")
            self.connection.put(bin_file, ANIM_REMOTE_FOLDER + bin_file.name)
        self.ejecuta('rm /home/angel/midi_notes_log.csv')