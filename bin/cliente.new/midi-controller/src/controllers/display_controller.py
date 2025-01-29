import asyncio
from pathlib import Path
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class DisplayController:
    """Controls display operations for image handling and rendering."""
    
    def __init__(self, framebuffer_service, image_path: str = "/home/angel/images"):
        """
        Initialize the display controller.
        
        Args:
            framebuffer_service: Service to handle framebuffer operations
            image_path: Base path for image files
        """
        self.framebuffer_service = framebuffer_service
        self.image_path = Path(image_path)
        self.current_task: Optional[asyncio.Task] = None

    async def activate_image(self, image_id: int, velocity: int) -> None:
        """
        Activate an image with the given ID and velocity.
        
        Args:
            image_id: ID of the image to display
            velocity: Velocity parameter for the image display
        """
        try:
            if velocity == 127:
                velocity = 0
            await self.handle_image(image_id, velocity, 50)
        except Exception as e:
            logger.error(f"Error activating image {image_id}: {e}")

    async def handle_image(self, image_id: int, loop: int, delay: int) -> None:
        """
        Handle the image display sequence.
        
        Args:
            image_id: ID of the image to display
            loop: Number of times to loop the image
            delay: Delay between frames in milliseconds
        """
        try:
            # Cancel any existing image task
            if self.current_task and not self.current_task.done():
                self.current_task.cancel()
                await asyncio.sleep(0)  # Allow cancellation to process
            
            self.current_task = asyncio.create_task(self._display_sequence(image_id, loop, delay))
            await self.current_task
        except asyncio.CancelledError:
            logger.debug(f"Image sequence {image_id} cancelled")
        except Exception as e:
            logger.error(f"Error handling image {image_id}: {e}")

    async def _display_sequence(self, image_id: int, loop: int, delay: int) -> None:
        """
        Internal method to handle the image display sequence.
        
        Args:
            image_id: ID of the image to display
            loop: Number of times to loop the image
            delay: Delay between frames in milliseconds
        """
        try:
            self.framebuffer_service.clear()
            if loop <= 0:
                img_data = self.load_image(image_id)
                if img_data:
                    self.framebuffer_service.draw_image(img_data)
            else:
                for _ in range(loop):
                    img_data = self.load_image(image_id)
                    if img_data:
                        self.framebuffer_service.draw_image(img_data)
                    await asyncio.sleep(delay / 1000)
        except Exception as e:
            logger.error(f"Error in display sequence for image {image_id}: {e}")

    def load_image(self, image_id: int) -> Optional[bytes]:
        """
        Load image data from file.
        
        Args:
            image_id: ID of the image to load
            
        Returns:
            Optional[bytes]: Image data if successful, None otherwise
        """
        try:
            image_path = self.image_path / f"{image_id:03d}.bin"
            if not image_path.exists():
                logger.warning(f"Image file not found: {image_path}")
                return None
                
            with open(image_path, "rb") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error loading image {image_id}: {e}")
            return None