import asyncio
import signal
from config.settings import load_config
from controllers.gpio_controller import GPIOController
from services.tcp_service import TcpService
from utils.logger import setup_logger, logger  # Added logger import

async def shutdown(loop, signal=None):
    if signal:
        logger.info(f"Received exit signal {signal.name}...")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]
    logger.info("Canceling outstanding tasks")
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("Tasks canceled, stopping loop")
    loop.stop()

def setup_signal_handlers(loop):
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.ensure_future(shutdown(loop, s)))

if __name__ == '__main__':
    setup_logger()
    config = load_config()
    
    gpio_controller = GPIOController(config['instruments'], config['tiempo'])
    tcp_service = TcpService(config['server_addr'], config['server_port'])

    loop = asyncio.get_event_loop()
    setup_signal_handlers(loop)

    try:
        loop.run_until_complete(tcp_service.start())
    except KeyboardInterrupt:
        logger.error("Program interrupted")
    finally:
        logger.info("Cleaning up before exit")
        gpio_controller.cleanup()