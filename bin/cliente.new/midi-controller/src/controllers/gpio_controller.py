import asyncio
import logging
from typing import Union, List
import RPi.GPIO as GPIO

logger = logging.getLogger(__name__)

class GPIOController:
    """Controller for handling GPIO operations for instruments."""

    def __init__(self, instruments: dict, tiempo: float):
        """
        Initialize GPIO controller.
        
        Args:
            instruments: Dictionary mapping instrument IDs to GPIO pins
            tiempo: Time duration for instrument activation
        """
        self.instruments = instruments
        self.tiempo = tiempo
        self.init_gpio()

    def init_gpio(self) -> None:
        """Initialize GPIO pins for all configured instruments."""
        try:
            GPIO.setmode(GPIO.BCM)
            for pin in self.instruments.values():
                GPIO.setup(pin, GPIO.OUT)
                GPIO.output(pin, GPIO.LOW)
            logger.info("GPIO initialization completed")
        except Exception as e:
            logger.error(f"Failed to initialize GPIO: {e}")
            raise

    async def activate_instrumento(self, ins: Union[int, List[int]]) -> None:
        """
        Activate one or more instruments by their GPIO pins.
        
        Args:
            ins: Single pin number or list of pin numbers to activate
        """
        if isinstance(ins, int):
            ins = [ins]
        
        try:
            # Activate pins
            for pin in ins:
                GPIO.output(pin, GPIO.HIGH)
                logger.debug(f"Pin {pin} activated")
            
            # Wait for specified duration
            await asyncio.sleep(self.tiempo)
            
            # Deactivate pins
            for pin in ins:
                GPIO.output(pin, GPIO.LOW)
                logger.debug(f"Pin {pin} deactivated")
                
        except Exception as e:
            logger.error(f"Error during instrument activation: {e}")
            # Ensure pins are set low in case of error
            for pin in ins:
                try:
                    GPIO.output(pin, GPIO.LOW)
                except:
                    pass
            raise

    def cleanup_gpio(self) -> None:
        """Clean up GPIO resources."""
        try:
            GPIO.cleanup()
            logger.info('GPIO cleanup completed')
        except Exception as e:
            logger.error(f"Error during GPIO cleanup: {e}")