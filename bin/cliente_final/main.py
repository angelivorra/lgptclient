#!/usr/bin/env python3
"""
Cliente TCP con orquestación de eventos GPIO y Display.

Punto de entrada principal que integra todos los componentes:
- Cliente TCP para conexión con servidor
- Configuración de instrumentos/pines
- Scheduler para ejecución temporizada
- Ejecutor GPIO para hardware
- Ejecutor Display para framebuffer
- Orquestador de eventos

Protocolo de mensajes (ASCII, terminados en \\n):
  CONFIG,<delay_ms>,<debug>,<ruido>,<pantalla>
  SYNC,<server_ts_ms>
  NOTA,<server_ts_ms>,<note>,<channel>,<velocity>
  CC,<server_ts_ms>,<value>,<channel>,<controller>
  START,<server_ts_ms>
  STOP,<server_ts_ms>    <- Limpia cola de eventos pendientes
  END,<server_ts_ms>
"""
import asyncio
import os
import logging
from pathlib import Path

# Configuración del servidor
SERVER_HOST = os.environ.get("SERVER_HOST", "192.168.0.2")
SERVER_PORT = int(os.environ.get("SERVER_PORT", "8888"))

# Configuración de sincronización NTP
ENABLE_NTP_SYNC = os.environ.get("ENABLE_NTP_SYNC", "1") == "1"

# Configuración de modo simulación
SIMULATE_GPIO = os.environ.get("SIMULATE_GPIO", "0") == "1"
SIMULATE_DISPLAY = os.environ.get("SIMULATE_DISPLAY", "0") == "1"

# Configuración de medios
MEDIA_BASE_PATH = os.environ.get("MEDIA_BASE_PATH", "/home/angel/images")

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)-7s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("cliente.main")

# Importar componentes
from config_loader import ConfigLoader
from scheduler import Scheduler
from gpio_executor import GPIOExecutor
from media_manager import MediaManager
from display_executor import DisplayExecutor
from event_orchestrator import EventOrchestrator


class MIDIClient:
    """Cliente MIDI completo con GPIO, display y scheduling."""
    
    def __init__(self, config_path: str = "config.json"):
        """
        Args:
            config_path: Ruta al archivo de configuración JSON
        """
        # Cargar configuración
        logger.info("📋 Cargando configuración...")
        self.config = ConfigLoader(config_path)
        logger.info(f"   Instrumentos: {len(self.config.instruments)}")
        logger.info(f"   Pines configurados: {len(self.config.pines)}")
        
        # Crear scheduler
        self.scheduler = Scheduler()
        
        # Crear ejecutor GPIO
        self.gpio_executor = GPIOExecutor(simulate=SIMULATE_GPIO)
        
        # Inicializar GPIO con todos los pines configurados
        all_pins = list(self.config.pines.keys())
        self.gpio_executor.initialize(all_pins)
        
        # Crear gestor de medios y ejecutor de display
        logger.info("📺 Inicializando sistema de display...")
        self.media_manager = MediaManager(MEDIA_BASE_PATH, max_image_cache=10)
        self.display_executor = DisplayExecutor(simulate=SIMULATE_DISPLAY)
        logger.info(f"   Ruta de medios: {MEDIA_BASE_PATH}")
        logger.info(f"   Modo display: {'Simulación' if SIMULATE_DISPLAY else 'Real'}")
        
        # Crear orquestador
        self.orchestrator = EventOrchestrator(
            config=self.config,
            scheduler=self.scheduler,
            gpio_executor=self.gpio_executor,
            media_manager=self.media_manager,
            display_executor=self.display_executor,
            base_delay_ms=1000
        )
    
    async def synchronize_system_time(self):
        """Sincroniza el reloj del sistema con el servidor usando ntpdate."""
        if not ENABLE_NTP_SYNC:
            logger.info("⏰ Sincronización NTP desactivada (ENABLE_NTP_SYNC=0)")
            return
        
        logger.info("⏰ Sincronizando reloj del sistema con el servidor...")
        
        try:
            process = await asyncio.create_subprocess_exec(
                'sudo', 'ntpdate', '-u', SERVER_HOST,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info("✅ Reloj del sistema sincronizado exitosamente")
                if stdout:
                    output = stdout.decode().strip()
                    logger.info(f"   {output}")
            else:
                error_msg = stderr.decode().strip() if stderr else "Sin detalles de error"
                logger.warning(f"⚠️  No se pudo sincronizar el reloj del sistema")
                logger.warning(f"   Error: {error_msg}")
                
        except FileNotFoundError:
            logger.error("❌ ntpdate no está instalado")
            logger.error("   Instala con: sudo apt-get install ntpdate")
            
        except Exception as e:
            logger.error(f"❌ Error sincronizando tiempo: {e}")
    
    async def process_message(self, line: str):
        """Procesa una línea recibida del servidor."""
        line = line.strip()
        if not line:
            return
        
        parts = line.split(',')
        if not parts:
            return
        
        msg_type = parts[0]
        
        try:
            if msg_type == 'CONFIG' and len(parts) >= 5:
                debug = parts[2].lower() in ('1', 'true', 't', 'yes', 'y')
                ruido = parts[3].lower() in ('1', 'true', 't', 'yes', 'y')
                pantalla = parts[4].lower() in ('1', 'true', 't', 'yes', 'y')
                logger.info(f"⚙️  CONFIG: debug={debug}, ruido={ruido}, pantalla={pantalla}")
                
            elif msg_type == 'SYNC' and len(parts) >= 2:
                logger.debug("SYNC ignorado")
                
            elif msg_type == 'NOTA' and len(parts) >= 5:
                server_ts_ms = int(parts[1])
                note = int(parts[2])
                channel = int(parts[3])
                velocity = int(parts[4])
                
                logger.debug(f"🎵 NOTA {note} (canal {channel}, vel {velocity})")
                self.orchestrator.handle_nota(server_ts_ms, note, channel, velocity)
                
            elif msg_type == 'CC' and len(parts) >= 5:
                server_ts_ms = int(parts[1])
                value = int(parts[2])
                channel = int(parts[3])
                controller = int(parts[4])
                
                logger.debug(f"🎛️  CC {controller}={value} (canal {channel})")
                self.orchestrator.handle_cc(server_ts_ms, value, channel, controller)
                
            elif msg_type == 'START' and len(parts) >= 2:
                server_ts_ms = int(parts[1])
                self.orchestrator.handle_start(server_ts_ms)
                
            elif msg_type == 'STOP' and len(parts) >= 2:
                server_ts_ms = int(parts[1])
                self.orchestrator.handle_stop(server_ts_ms)
                
            elif msg_type == 'END' and len(parts) >= 2:
                server_ts_ms = int(parts[1])
                self.orchestrator.handle_end(server_ts_ms)
                
            else:
                logger.debug(f"Mensaje desconocido o incompleto: {line}")
                
        except (ValueError, IndexError) as e:
            logger.error(f"Error parseando mensaje '{line}': {e}")
    
    async def run(self):
        """Loop principal del cliente."""
        logger.info("=" * 60)
        logger.info("Cliente MIDI con GPIO - Iniciando")
        logger.info("=" * 60)
        logger.info(f"Servidor: {SERVER_HOST}:{SERVER_PORT}")
        logger.info(f"Sincronización NTP: {'Activada' if ENABLE_NTP_SYNC else 'Desactivada'}")
        logger.info(f"Modo GPIO: {'Simulación' if SIMULATE_GPIO else 'Real'}")
        logger.info("")
        
        # Iniciar scheduler en background
        await self.scheduler.start()
        
        try:
            while True:
                try:
                    logger.info(f"🔌 Conectando a {SERVER_HOST}:{SERVER_PORT}...")
                    
                    # Actualizar estado de conexión (intentando conectar)
                    self.orchestrator.set_connection_status(False, SERVER_HOST, SERVER_PORT)
                    
                    reader, writer = await asyncio.open_connection(SERVER_HOST, SERVER_PORT)
                    logger.info("✅ Conectado al servidor")
                    
                    # Actualizar estado de conexión (conectado)
                    self.orchestrator.set_connection_status(True, SERVER_HOST, SERVER_PORT)
                    
                    logger.info("")
                    
                    try:
                        # Sincronizar tiempo del sistema
                        await self.synchronize_system_time()
                        
                        logger.info("")
                        logger.info("📡 Esperando mensajes del servidor...")
                        logger.info("-" * 60)
                        logger.info("")
                        
                        # Loop de recepción de mensajes
                        while True:
                            line = await reader.readline()
                            if not line:
                                logger.warning("❌ Servidor cerró la conexión")
                                break
                            
                            try:
                                text = line.decode().strip()
                                await self.process_message(text)
                            except UnicodeDecodeError as e:
                                logger.error(f"Error decodificando mensaje: {e}")
                                continue
                                
                    except Exception as e:
                        logger.error(f"❌ Error en loop de lectura: {e}")
                    finally:
                        writer.close()
                        await writer.wait_closed()
                        logger.info("🔌 Conexión cerrada")
                        
                        # Actualizar estado de conexión (desconectado)
                        self.orchestrator.set_connection_status(False, SERVER_HOST, SERVER_PORT)
                        
                except Exception as e:
                    logger.error(f"❌ Error de conexión: {e}")
                    # Actualizar estado de conexión (error)
                    self.orchestrator.set_connection_status(False, SERVER_HOST, SERVER_PORT)
                
                # Esperar antes de reintentar
                logger.info("")
                logger.info("⏳ Reintentando conexión en 3 segundos...")
                logger.info("")
                await asyncio.sleep(3)
                
        finally:
            # Cleanup orquestador (detiene status screen)
            self.orchestrator.cleanup()
            
            # Detener scheduler
            await self.scheduler.stop()
            
            # Cleanup GPIO
            self.gpio_executor.cleanup()
            
            # Cleanup display
            self.display_executor.cleanup()


async def main():
    """Punto de entrada principal."""
    # Cambiar al directorio del script para encontrar config.json
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    client = MIDIClient()
    try:
        await client.run()
    except KeyboardInterrupt:
        logger.info("")
        logger.info("=" * 60)
        logger.info("👋 Cliente detenido por el usuario")
        logger.info("=" * 60)


if __name__ == '__main__':
    asyncio.run(main())
