#!/usr/bin/env /home/angel/lgptclient/venv/bin/python3
from subprocess import run
import subprocess
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

        except KeyboardInterrupt:
            sys.exit()
        except Exception as e:
            print(f"An error occurred: {e}")

def restart_server():
  print('Restart Server...')
  run(["sudo", "killall", "arecord"])
  run(["sudo", "killall", "aplay"])
  run(["sudo", "/etc/init.d/alsa-utils", "stop"])
  run(["sudo", "/etc/init.d/alsa-utils", "start"])
  subprocess.Popen("sudo arecord -D hw:Loopback,1 -f cd | sudo aplay -D movida", shell=True)
  # arecord_cmd = "sudo arecord -D hw:Loopback,1 -f cd -B 5000 -F 2500"
  # aplay_cmd = "sudo aplay -D movida -B 5000 -F 2500"
  # subprocess.Popen(f"{arecord_cmd} | {aplay_cmd}", shell=True)
  run(["sudo", "systemctl", "restart", "servidor"])

if __name__ == "__main__":
  main()
