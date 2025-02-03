from actualiza_maleta import actualiza_maleta
from actualiza_sombrilla import actualiza_sombrilla
import argparse

parser = argparse.ArgumentParser(prog='Actualiza')
parser.add_argument('--pip', default=False)
args = parser.parse_args()

RESTART_SERVICE = True
IMG = False
PIP = False

if __name__ == "__main__":
    #actualiza_maleta(restart_service=RESTART_SERVICE, generate_images=IMG, upload_images=IMG, pip=PIP)
    actualiza_sombrilla(restart_service=RESTART_SERVICE, generate_images=IMG, upload_images=IMG, pip=PIP)