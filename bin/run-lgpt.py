#!/usr/bin/env /home/angel/lgptclient/venv/bin/python3
from subprocess import run
import subprocess
import sys

LGPT = '/home/angel/lgptclient/lgpt/bin/lgpt.rpi-exe'
DATABASE = "/home/angel/lgpt.data"
LOG_FILE = "/home/angel/lgpt.log"
EXEC_LOG_FILE = "/home/angel/lgpt.exec.log"

def main():
    while True:
        restart_server()
        try:
            with open(EXEC_LOG_FILE, "w") as log_file:
                data = run(LGPT, capture_output=True, shell=True)

                output = data.stdout.splitlines()
                errors = data.stderr.splitlines()

                log_file.write("OUTPUT\n")
                log_file.write("------\n")
                log_file.write(data.stdout)
                log_file.write('ERRORES\n')
                log_file.write('-------\n')
                log_file.write(data.stderr)

                log_file.write(f"ERROR CODE = {data.returncode}\n")

        except KeyboardInterrupt:
            sys.exit()
        except Exception as e:
            print(f"Exception: {e}")

def restart_server():
    with open(LOG_FILE, "w") as log_file:
        log_file.write("Inicio...\n")
        result = run(["pgrep", "aplay"], capture_output=True, text=True)
        if result.stdout:
            print("Kill aplay")
            log_file.write("Kill aplay\n")
            run(["sudo", "killall", "aplay"])
        result = run(["pgrep", "arecord"], capture_output=True, text=True)
        if result.stdout:
            log_file.write("Kill arecord\n")
            print("Kill arecord")
            run(["sudo", "killall", "arecord"])
        
    run(["sudo", "/etc/init.d/alsa-utils", "stop"])
    run(["sudo", "/etc/init.d/alsa-utils", "start"])
    with open("/home/angel/arecord.log", "w") as arecord_log:
        subprocess.Popen("sudo arecord -D hw:Loopback,1 -f cd | sudo aplay -D movida", shell=True, stdout=arecord_log, stderr=arecord_log)
    run(["sudo", "systemctl", "restart", "servidor"])

if __name__ == "__main__":
  main()
