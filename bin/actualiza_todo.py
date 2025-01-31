from actualiza_maleta import actualiza_maleta
from actualiza_sombrilla import actualiza_sombrilla
import argparse

parser = argparse.ArgumentParser(prog='Actualiza')
parser.add_argument('--pip', default=False)
args = parser.parse_args()



if __name__ == "__main__":
    #actualiza_maleta()
    actualiza_sombrilla(restart_service=True, generate_images=True, upload_images=False, pip=False)