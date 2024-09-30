#!/usr/bin/env /home/angel/lgptclient/venv/bin/python3
import os
from subprocess import run
import csv
import time
import pysftp
import paramiko
import statistics
from tabulate import tabulate

LGPT = '/home/angel/lgptclient/lgpt/bin/lgpt.rpi-exe'
DATABASE = "/home/angel/lgpt.data"
TMP_FILE = '/tmp/debug_notes.tmp'

class SftpCliente:
    def __init__(self, ip, nombre):
        self.connection = None
        self.hostname = ip
        self.username = "angel"
        self.port = 22
        self.nombre = nombre

    def connect(self):
        """Connects to the sftp server and returns the sftp connection object"""

        try:
            # Get the sftp connection object
            self.connection = pysftp.Connection(
                host=self.hostname,
                username=self.username,
                port=self.port,
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

            # Download file from SFTP
            self.connection.get("/home/angel/midi_notes_log.csv", f"/home/angel/midi.notes.{self.nombre}.csv")
            print(f"{self.nombre} Descargado")

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

def activa_debug(host):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host)

    ejecuta(ssh, 'touch /tmp/debug_notes.tmp')    
    ejecuta(ssh, 'sudo systemctl restart cliente')
    ejecuta(ssh, 'sudo fbi -a /home/angel/images/terminal-bg.jpg -T 1 --nocomments --noverbose')
    time.sleep(2)
    status = ejecuta(ssh, 'sudo systemctl status cliente')
    output=''
    for line in status:
        output=output+line
    print(output)

def read_csv_to_dict(filename):
    """Read a CSV file and return a list of dictionaries."""
    with open(filename, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        return [dict(row) for row in reader]

def analyze_data(nombre):
    # Load the data from the uploaded CSV files
    midi_notes_log = read_csv_to_dict("/home/angel/midi_notes_log.csv")
    midi_notes_maleta = read_csv_to_dict(f"/home/angel/midi.notes.{nombre}.csv")

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
    stats_summary = [
        ["Notes Sent", total_notes_sent],
        ["Notes Received", total_notes_received],
        ["Percent Received", int(percent_notes_received)],
        ["Min Time Difference (ms)", int(min_time_difference)],
        ["Max Time Difference (ms)", int(max_time_difference)],
        ["Average Time Difference (ms)", int(avg_time_difference)],
    ]
    
    return stats_summary


def main():    
    sftp = SftpCliente("192.168.0.3", "maleta")
    sftp.connect()
    sftp.download()
    sftp.disconnect()
    print("Maleta")
    maleta = analyze_data("maleta")
    print(tabulate(maleta))

  

if __name__ == "__main__":
  main()
