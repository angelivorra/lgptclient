#!/usr/bin/env python3
"""
Script de prueba para verificar la animación por defecto.
"""
import time
import logging
import asyncio

from config_loader import ConfigLoader
from scheduler import Scheduler
from gpio_executor import GPIOExecutor
from media_manager import MediaManager
from display_executor import DisplayExecutor
from event_orchestrator import EventOrchestrator

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)-7s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger("test")

async def main():
    logger.info("="*60)
    logger.info("TEST: Animación por defecto")
    logger.info("="*60)
    
    # Inicializar componentes
    config = ConfigLoader()
    scheduler = Scheduler()
    await scheduler.start()
    
    gpio_executor = GPIOExecutor(simulate=True)
    gpio_executor.initialize(config.get_all_pins())
    
    media_manager = MediaManager("/home/angel/lgptclient/img_output/sombrilla")
    display_executor = DisplayExecutor(simulate=True)
    
    orchestrator = EventOrchestrator(
        config=config,
        scheduler=scheduler,
        gpio_executor=gpio_executor,
        media_manager=media_manager,
        display_executor=display_executor
    )
    
    logger.info("\n--- Test 1: Animación al iniciar (ya debería estar corriendo) ---")
    await asyncio.sleep(3)
    
    logger.info("\n--- Test 2: Simular evento CC (debería cambiar animación) ---")
    current_ts = int(time.time() * 1000)
    orchestrator.handle_cc(current_ts, 1, 0, 3)  # CC 3/1
    await asyncio.sleep(3)
    
    logger.info("\n--- Test 3: Simular evento END (debería volver a animación por defecto) ---")
    orchestrator.handle_end(current_ts + 3000)
    await asyncio.sleep(3)
    
    logger.info("\n--- Estadísticas ---")
    orchestrator.print_stats()
    display_executor.print_stats()
    
    # Cleanup
    await scheduler.stop()
    gpio_executor.cleanup()
    display_executor.cleanup()
    
    logger.info("\n✅ Test completado")

if __name__ == '__main__':
    asyncio.run(main())
