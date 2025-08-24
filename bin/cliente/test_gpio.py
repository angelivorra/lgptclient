#!/usr/bin/env python3
import argparse
import logging
import time

import RPi.GPIO as GPIO


def init_gpio(pin: int) -> None:
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)


def cleanup_gpio() -> None:
    GPIO.cleanup()


def activate_pin(pin: int, duration_ms: int) -> None:
    # Ensure non-negative duration
    duration_ms = max(0, int(duration_ms))
    init_gpio(pin)
    try:
        logging.info(f"Activating GPIO {pin} for {duration_ms} ms")
        GPIO.output(pin, GPIO.HIGH)
        time.sleep(duration_ms / 1000.0)
    finally:
        GPIO.output(pin, GPIO.LOW)
        cleanup_gpio()
        logging.info("GPIO deactivated and cleaned up")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Activa un pin GPIO (BCM) durante un número de milisegundos y luego lo desactiva."
        )
    )
    parser.add_argument("pin", type=int, help="Número de pin GPIO (modo BCM)")
    parser.add_argument(
        "milisegundos", type=int, help="Duración en milisegundos para activar el pin"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Muestra logs de depuración"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )
    try:
        activate_pin(args.pin, args.milisegundos)
    except KeyboardInterrupt:
        logging.warning("Interrumpido por el usuario; limpiando GPIO…")
        try:
            GPIO.output(args.pin, GPIO.LOW)
        except Exception:
            pass
        cleanup_gpio()


if __name__ == "__main__":
    main()
