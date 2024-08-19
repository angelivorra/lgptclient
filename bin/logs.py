#10.42.0.73
import argparse
import csv
from openpyxl import Workbook
import pysftp
from urllib.parse import urlparse
import os
import paramiko

CSV_FILENAME = '/home/angel/midi_notes_log.csv'
TMP_FILENAME = '/tmp/midi_notes_log.csv'
resultado = '/home/angel/midi_notes_log.xlsx'

class Sftp:
    def __init__(self, hostname):
        self.connection = None
        self.hostname = hostname
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

    def download(self):
        try:
            if os.path.exists(TMP_FILENAME):
                os.unlink(TMP_FILENAME) # Remove the file if it exists

            self.connection.get(CSV_FILENAME, TMP_FILENAME) # Download file from SFTP server

        except Exception as err:
            raise Exception(err)


def ejecuta(ssh, comando):
    print(f"Ejecutamos Comando {comando}")
    stdin, stdout, stderr = ssh.exec_command(comando)
    exit_status = stdout.channel.recv_exit_status()
    if exit_status == 0:
        print("Hecho")
    else:
        print(f"Error {exit_status}")
        print(f"Errores {stderr}")
    

def process_csv_to_xlsx(input_filename, output_filename):
    wb = Workbook()
    ws = wb.active
    ws.title = "Data"

    with open(input_filename, mode='r') as infile:
        reader = csv.reader(infile)
        ws.append(["Timestamp", "Note", "Received Timestamp", "Delay", "Diferencia", "Notas", "Realidad", "Bien"])
        ant_tiempo = 0
        for row in reader:            
            col1 = int(row[0])
            col2 = int(row[1])
            col3 = int(row[2])
            col4 = col1 - col3
            col5 = int( col1 - ant_tiempo )
            col6 = int(col5 / 104)
            if col6 < 1:
                col6 = 1
            col7 = col2 - 59
            col8 = col7 - col6
            
            ant_tiempo = col3
            ws.append([col1, col2, col3, col4, col5, col6, col7, col8])
    
    wb.save(output_filename)   

if __name__ == "__main__":
    
    sftp = Sftp(hostname="10.42.0.73")
    # Connect to SFTP
    sftp.connect()
    sftp.download()
    sftp.disconnect()
    process_csv_to_xlsx(TMP_FILENAME, "/home/angel/tiempos.maleta.xlsx")
    
