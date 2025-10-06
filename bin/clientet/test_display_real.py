#!/usr/bin/env python3
"""
Script de prueba para verificar que las imágenes se muestran en el framebuffer real.
"""
import time
import logging
import sys

from media_manager import MediaManager
from display_executor import DisplayExecutor

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)-7s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger("test")

def main():
    # Ruta de imágenes
    MEDIA_PATH = "/home/angel/lgptclient/img_output/sombrilla"
    
    # Inicializar (modo REAL, no simulación)
    logger.info("🚀 Iniciando test en MODO REAL (framebuffer /dev/fb0)")
    media = MediaManager(MEDIA_PATH)
    display = DisplayExecutor(fb_device="/dev/fb0", simulate=False)
    
    try:
        # Test 1: Mostrar imagen
        logger.info("\n=== Test 1: Mostrar imagen 001/001 ===")
        img = media.get_image(1, 1)
        if img:
            display.show_image(img, 1, 1)
            logger.info("✅ Imagen 1/1 mostrada, esperando 2 segundos...")
            time.sleep(2)
        else:
            logger.error("❌ No se pudo cargar imagen 1/1")
        
        # Test 2: Cambiar imagen
        logger.info("\n=== Test 2: Cambiar a imagen 001/007 ===")
        img2 = media.get_image(1, 7)
        if img2:
            display.show_image(img2, 1, 7)
            logger.info("✅ Imagen 1/7 mostrada, esperando 2 segundos...")
            time.sleep(2)
        else:
            logger.error("❌ No se pudo cargar imagen 1/7")
        
        # Test 3: Mostrar animación
        logger.info("\n=== Test 3: Reproducir animación 003/001 ===")
        anim = media.get_animation(3, 1)
        if anim:
            display.play_animation(anim)
            logger.info(f"✅ Animación 3/1 iniciada ({len(anim.frames)} frames @ 30fps)")
            logger.info("   Dejando reproducir 5 segundos...")
            time.sleep(5)
        else:
            logger.error("❌ No se pudo cargar animación 3/1")
        
        # Test 4: Parar animación con imagen
        logger.info("\n=== Test 4: Parar animación con imagen 001/002 ===")
        img3 = media.get_image(1, 2)
        if img3:
            display.show_image(img3, 1, 2)
            logger.info("✅ Imagen 1/2 mostrada (animación parada)")
            time.sleep(2)
        else:
            logger.error("❌ No se pudo cargar imagen 1/2")
        
        # Mostrar estadísticas
        logger.info("\n" + "="*60)
        display.print_stats()
        media.print_stats()
        
    except KeyboardInterrupt:
        logger.info("\n⚠️  Test interrumpido por usuario")
    except Exception as e:
        logger.error(f"\n❌ Error durante el test: {e}", exc_info=True)
    finally:
        display.cleanup()
        logger.info("\n✅ Test completado")

if __name__ == '__main__':
    main()
