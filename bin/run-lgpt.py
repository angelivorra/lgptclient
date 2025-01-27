#!/usr/bin/env /home/angel/lgptclient/venv/bin/python3
from subprocess import run
import sys

LGPT = '/home/angel/lgptclient/lgpt/bin/lgpt.rpi-exe'
DATABASE = "/home/angel/lgpt.data"

def main():
  while True:
    restart_server()
    try:
      data = run(LGPT, capture_output=True, shell=True)

      output = data.stdout.splitlines()
      errors = data.stderr.splitlines()

      print('output')
      print(data.stdout)
      print('Errores')
      print(data.stderr)

      print(data.returncode)

    except (EOFError, KeyboardInterrupt):
      pass

def restart_server():
  print('Restart Server...')
  run(["sudo", "systemctl", "restart", "servidor"])

if __name__ == "__main__":
  main()
