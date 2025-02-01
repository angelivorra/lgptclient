import RPi.GPIO as GPIO
import time

# Define the array of GPIO pins
pin = 23  # Cambia estos números por los pines que necesites
tiempo = 0.05  # Cambia este valor por el tiempo que necesites
pausa = 1  # Cambia este valor por el tiempo que necesites

def init_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)

def activate_pins_sequence():
    GPIO.output(pin, GPIO.HIGH)
    time.sleep(tiempo)  # Activa el pin durante 1 segundo
    GPIO.output(pin, GPIO.LOW)
    time.sleep(pausa)  # Pausa de 1 segundo antes de activar el siguiente pin

def cleanup_gpio():
    GPIO.cleanup()

if __name__ == "__main__":
    try:
        init_gpio()
        while True:
            activate_pins_sequence()
    except KeyboardInterrupt:
        pass
    finally:
        cleanup_gpio()