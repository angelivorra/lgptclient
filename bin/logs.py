#10.42.0.73
import pysftp
from urllib.parse import urlparse
import os
import pandas as pd

CSV_FILENAME = '/home/angel/midi_notes_log.csv'
TMP_FILENAME = '/home/angel/midi_notes_maleta.csv'
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
            self.connection.get("/home/angel/cliente.log", "/home/angel/cliente.log") # Download file from SFTP server

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
    

def analize_data():
    # Load the data from the uploaded CSV files
    midi_notes_log = pd.read_csv(CSV_FILENAME)
    midi_notes_maleta = pd.read_csv(TMP_FILENAME)
    
    # Convert timestamps to integers for accurate calculation (if they aren't already)
    midi_notes_log['timestamp_sent'] = midi_notes_log['timestamp_sent'].astype(int)
    midi_notes_maleta['timestamp_sent'] = midi_notes_maleta['timestamp_sent'].astype(int)
    midi_notes_maleta['timestamp_received'] = midi_notes_maleta['timestamp_received'].astype(int)

    # Calculate the number of notes sent
    total_notes_sent = midi_notes_log.shape[0]

    # Calculate the number of notes received
    total_notes_received = midi_notes_maleta.shape[0]

    # Calculate the percentage of notes received
    percent_notes_received = (total_notes_received / total_notes_sent) * 100

    # Merge the log and maleta data on the timestamp and note to find matching pairs
    merged_data = pd.merge(midi_notes_log, midi_notes_maleta, on=['timestamp_sent', 'note'])

    # Calculate the time difference between sent and received timestamps
    merged_data['time_difference'] = merged_data['timestamp_received'] - merged_data['timestamp_sent']

    # Calculate min, max, and average time differences
    min_time_difference = merged_data['time_difference'].min()
    max_time_difference = merged_data['time_difference'].max()
    avg_time_difference = merged_data['time_difference'].mean()

    # Summarize statistics in a dictionary
    stats_summary = {
        "Total Notes Sent": total_notes_sent,
        "Total Notes Received": total_notes_received,
        "Percent Notes Received": percent_notes_received,
        "Min Time Difference (ms)": min_time_difference,
        "Max Time Difference (ms)": max_time_difference,
        "Average Time Difference (ms)": avg_time_difference,
    }
    
    return stats_summary





if __name__ == "__main__":
    
    #sftp = Sftp(hostname="10.42.0.73")
    # Connect to SFTP
    #sftp.connect()
    #sftp.download()
    #sftp.disconnect()
    
    print(analize_data())
    
