from pathlib import Path
import paramiko
import pysftp
import time
from datetime import datetime

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
        print(f"\n[EXEC] {comando}")
        start = time.time()
        stdin, stdout, stderr = self.ssh.exec_command(comando, timeout=30)
        exit_status = stdout.channel.recv_exit_status()
        duration = time.time() - start
        
        if exit_status == 0:
            print(f"  ✓ Success ({duration:.1f}s)")
            return stdout.readlines()
        else:
            print(f"  ✗ Failed ({duration:.1f}s)")
            print(f"  Error: {stderr.readlines()}")
            return False

    def update_pyton(self):
        print("\n=== Python Environment Update ===")
        start = time.time()
        steps = 0
        commands = [
            'python3 -m pip cache purge',
            'rm -r /home/angel/venv',
            'python3 -m venv /home/angel/venv',
            '/home/angel/venv/bin/pip3 install --upgrade pip',
            '/home/angel/venv/bin/pip3 install -r /home/angel/requirements.txt'
        ]
        
        for cmd in commands:
            if self.ejecuta(cmd):
                steps += 1
                
        print(f"\n=== Update Complete ===")
        print(f"Steps completed: {steps}/{len(commands)}")
        print(f"Total time: {time.time()-start:.1f}s")

    def disconnect(self):
        """Closes the sftp connection"""
        self.connection.close()
        print(f"Disconnected from host {self.hostname}")

    def update_sources(self):
        print("\n=== Source Files Update ===")
        start = time.time()
        files = {
            "main_server.py": ("/home/angel/lgptclient/bin/cliente/main_server.py", "/home/angel/bin/main_server.py"),
            "image_events.py": ("/home/angel/lgptclient/bin/cliente/image_events.py", "/home/angel/bin/image_events.py"),
            "gpio_events.py": ("/home/angel/lgptclient/bin/cliente/gpio_events.py", "/home/angel/bin/gpio_events.py"),
            "config.json": (f"/home/angel/lgptclient/bin/cliente.{self.cliente}.json", "/home/angel/config.json"),
            "requirements.txt": (f"/home/angel/lgptclient/requirements_{self.cliente}.txt", "/home/angel/requirements.txt")
        }
        
        transferred = 0
        for name, (src, dest) in files.items():
            print(f"\nTransferring {name}...")
            try:
                self.connection.put(src, dest)
                print(f"  ✓ Success")
                transferred += 1
            except Exception as e:
                print(f"  ✗ Failed: {str(e)}")
                
        print(f"\n=== Transfer Complete ===")
        print(f"Files transferred: {transferred}/{len(files)}")
        print(f"Total time: {time.time()-start:.1f}s")

    def upload_images(self):
        print("\n=== Uploading Images ===")
        start = time.time()
        IMG_FOLDER = Path(f"/home/angel/lgptclient/images{self.cliente}")
        ANIMACIONES_FOLDER = Path(f"/home/angel/lgptclient/animaciones")
        
        transferred = 0
        errors = 0
        
        for folder, remote_dest in [(IMG_FOLDER, REMOTE_FOLDER), (ANIMACIONES_FOLDER, ANIM_REMOTE_FOLDER)]:
            bin_files = list(folder.glob("*.bin"))
            print(f"\nProcessing {folder.name}: {len(bin_files)} files")
            
            for bin_file in bin_files:
                try:
                    print(f"  Uploading {bin_file.name}...")
                    self.connection.put(bin_file, remote_dest + bin_file.name)
                    print(f"    ✓ Success")
                    transferred += 1
                except Exception as e:
                    print(f"    ✗ Failed: {str(e)}")
                    errors += 1
                    
        self.ejecuta('rm /home/angel/midi_notes_log.csv')
        
        print(f"\n=== Upload Complete ===")
        print(f"Files transferred: {transferred}")
        print(f"Errors: {errors}")
        print(f"Total time: {time.time()-start:.1f}s")