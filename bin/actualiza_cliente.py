import time
import logging
from urllib.parse import urlparse
import paramiko
from genera_imagenes import convert_all_png_to_bin, generar_markdown_imagenes
from ftpcliente import SftpCliente

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def actualiza_cliente(generate_images=True, upload_images=True, restart_service=True, pip=False):
    """
    Update Sombrilla device with new images and code.
    
    Args:
        generate_images (bool): Convert PNG images to binary format
        upload_images (bool): Upload converted images to device
        restart_service (bool): Restart the client service
        pip (bool): Update Python packages
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        IP_SOMBRILLA = "192.168.0.3"
        
        if generate_images:
            convert_all_png_to_bin(
                "/home/angel/lgptclient/images/", 
                "/home/angel/lgptclient/imagesmaleta/", 
                800, 480, 
                invert=False
            )

        sftp = SftpCliente(IP_SOMBRILLA, "maleta")
        sftp.connect()    
        sftp.update_sources()
        
        if upload_images:        
            sftp.upload_images()
        
        if pip:
            sftp.update_pyton()

        if restart_service:
            sftp.ejecuta('sudo systemctl restart cliente')
            time.sleep(2)
            status = sftp.ejecuta('sudo systemctl status cliente')
            if status:
                logger.info("Service status:\n%s", "".join(status))
            else:
                logger.error("Failed to get service status")
                return False

        return True

    except Exception as e:
        logger.error("Error in actualiza_sombrilla: %s", str(e))
        return False

    finally:
        if 'sftp' in locals():
            try:
                sftp.close()
            except:
                pass
