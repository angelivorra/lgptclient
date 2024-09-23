#!/usr/bin/env /home/angel/lgptclient/venv/bin/python3
import os
from subprocess import run
import sys
import time

import paramiko

LGPT = '/home/angel/lgptclient/lgpt/bin/lgpt.rpi-exe'
DATABASE = "/home/angel/lgpt.data"
TMP_FILE = '/tmp/debug_notes.tmp'

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
    time.sleep(2)
    status = ejecuta(ssh, 'sudo systemctl status cliente')
    output=''
    for line in status:
        output=output+line
    print(output)


def main():    
    run(["touch", TMP_FILE])
    print('Restart Servidor...')
    run(["sudo", "systemctl", "restart", "servidor"])
    activa_debug("192.168.0.3")

    try:
      data = run(f"sudo  {LGPT}", capture_output=True, shell=True)

      output = data.stdout.splitlines()
      errors = data.stderr.splitlines()

      print('output')
      print(data.stdout)
      print('Errores')
      print(data.stderr)

      print(data.returncode)

    except (EOFError, KeyboardInterrupt):
      pass
    
    print("Fin del test")
    

  

if __name__ == "__main__":
  main()
