#10.42.0.73
import argparse
import pysftp
from urllib.parse import urlparse
import os

parser = argparse.ArgumentParser(prog='Actualiza')
parser.add_argument('ip')
args = parser.parse_args()

class Sftp:
    def __init__(self, hostname):
        self.connection = None
        self.hostname = args.ip
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
            self.connection.put("/home/angel/lgptclient/bin/lcd.py", "/home/angel/lcd.py")
            self.connection.put("/home/angel/lgptclient/bin/cliente-tcp.py", "/home/angel/cliente-tcp.py")
            self.connection.put("/home/angel/lgptclient/requirements.txt", "/home/angel/requirements.txt")
            print("upload completed")

        except Exception as err:
            raise Exception(err)

if __name__ == "__main__":
    
    sftp = Sftp(hostname=args.ip)

    # Connect to SFTP
    sftp.connect()
    sftp.upload()
    sftp.disconnect()