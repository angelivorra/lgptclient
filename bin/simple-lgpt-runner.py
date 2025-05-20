#!/usr/bin/env python3
import subprocess
import signal
import sys
import os

LGPT = '/home/angel/lgptclient/lgpt/bin/lgpt.rpi-exe'

process = None

def signal_handler(signum, frame):
    global process
    if process and process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=3)
        except Exception:
            pass
        if process.poll() is None:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except Exception:
                pass
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    with open("/home/angel/lgptclient/lgpt/bin/lgpt.err.log", "w") as logfile:
        process = subprocess.Popen(["sudo", LGPT], preexec_fn=os.setsid, stdout=logfile, stderr=logfile)
        process.wait()
