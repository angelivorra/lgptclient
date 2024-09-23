#10.42.0.73
import pysftp
from urllib.parse import urlparse
import os
import statistics

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
    

def analyze_data():
    # Load the data from the uploaded CSV files
    midi_notes_log = read_csv_to_dict(CSV_FILENAME)
    midi_notes_maleta = read_csv_to_dict(TMP_FILENAME)

    # Convert timestamps to integers for accurate calculation
    for note in midi_notes_log:
        note['timestamp_sent'] = int(note['timestamp_sent'])
    
    for note in midi_notes_maleta:
        note['timestamp_sent'] = int(note['timestamp_sent'])
        note['timestamp_received'] = int(note['timestamp_received'])

    # Calculate the number of notes sent
    total_notes_sent = len(midi_notes_log)

    # Calculate the number of notes received
    total_notes_received = len(midi_notes_maleta)

    # Calculate the percentage of notes received
    percent_notes_received = (total_notes_received / total_notes_sent) * 100 if total_notes_sent > 0 else 0

    # Create a list to hold merged data
    merged_data = []
    for sent in midi_notes_log:
        for received in midi_notes_maleta:
            if (sent['timestamp_sent'] == received['timestamp_sent'] and
                    sent['note'] == received['note']):
                merged_data.append({
                    'timestamp_sent': sent['timestamp_sent'],
                    'timestamp_received': received['timestamp_received']
                })

    # Calculate the time difference between sent and received timestamps
    time_differences = [
        received['timestamp_received'] - sent['timestamp_sent']
        for sent, received in zip(merged_data, merged_data)
    ]

    # Calculate min, max, and average time differences
    min_time_difference = min(time_differences) if time_differences else 0
    max_time_difference = max(time_differences) if time_differences else 0
    avg_time_difference = statistics.mean(time_differences) if time_differences else 0

    # Summarize statistics in a dictionary
    stats_summary = {
        "Total Notes Sent": total_notes_sent,
        "Total Notes Received": total_notes_received,
        "Percent Notes Received": percent_notes_received,
        "Min Time Difference (ms)": min_time_difference,
        "Max Time Difference (ms)": max_time_difference,
        "Average Time Difference (ms)": avg_time_difference,
    }


if __name__ == "__main__":
    
    #sftp = Sftp(hostname="10.42.0.73")
    # Connect to SFTP
    #sftp.connect()
    #sftp.download()
    #sftp.disconnect()
    
    print(analize_data())
    
