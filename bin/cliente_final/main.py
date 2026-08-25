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
  RCONFIG,<json>          <- Config íntegra de esta robota (al conectar, antes de NOTA)
  CALIB,<server_ts_ms>,<robot>,<pin>,<tiempo_ms>,<delay_ms>  <- Calibración en vivo
  CALTEST,<server_ts_ms>,<robot>,<pin>            <- Programa el pin (ts+1s-delay)

RCONFIG lo manda el sinte (fuente única de la config) sólo a esta robota al
conectar; sobreescribe la config local de arranque. CALIB/CALTEST van
dirigidos a un robot por su nombre (config.nombre, case-insensitive); el
cliente los ignora si no coincide. La calibración se PERSISTE en el sinte,
no en la robota.
"""
import asyncio
import json
import os
import time
import logging
from pathlib import Path

STATUS_FILE = "/tmp/cliente_status.json"

# Configuración del servidor
SERVER_HOST = os.environ.get("SERVER_HOST", "192.168.0.2")
SERVER_PORT = int(os.environ.get("SERVER_PORT", "8888"))

# Sincronización del reloj con el servidor.
# En vez de NTP (que necesitaría internet o un servidor NTP autoritativo en la
# LAN — no disponible aquí), ajustamos el reloj con la hora que el servidor manda
# por el propio socket en los mensajes SYNC. Funciona sin internet.
# ENABLE_NTP_SYNC se mantiene como alias por compatibilidad.
ENABLE_TIME_SYNC = os.environ.get(
    "ENABLE_TIME_SYNC", os.environ.get("ENABLE_NTP_SYNC", "1")
) == "1"
# Solo se ajusta el reloj si el desfase con el servidor supera este umbral (ms),
# para no pisar el reloj en cada heartbeat SYNC.
TIME_SYNC_THRESHOLD_MS = int(os.environ.get("TIME_SYNC_THRESHOLD_MS", "200"))

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
import timing_log   # LOG TEMPORAL de timing (quitar tras depurar)


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
        
        # Inicializar GPIO con los pines de la config local (fallback). Si no
        # hay config local, se inicializan al llegar el RCONFIG del sinte.
        self.gpio_executor.ensure_pins(self.config.pines.keys())
        
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
    
    def _write_status(self, debug: bool, ruido: bool, pantalla: bool):
        """Escribe el estado actual en /tmp/cliente_status.json para que Flask lo lea."""
        try:
            with open(STATUS_FILE, 'w') as f:
                json.dump({
                    "nombre":   self.config.nombre,
                    "debug":    debug,
                    "ruido":    ruido,
                    "pantalla": pantalla,
                }, f)
        except Exception as e:
            logger.warning(f"No se pudo escribir estado: {e}")

    async def sync_clock_to_server(self, server_ts_ms: int):
        """Ajusta el reloj del sistema a la hora del servidor (recibida por SYNC).

        Todo el timing del cliente compara timestamps absolutos del servidor con
        time.time() local, así que ambos relojes deben coincidir. Aquí no usamos
        NTP: tomamos la hora que el servidor manda por el socket y la aplicamos con
        'date -s' (coreutils, siempre presente; requiere sudo sin contraseña, que
        las robotas ya tienen). Robusto sin internet.
        """
        if not ENABLE_TIME_SYNC:
            return

        local_ms = time.time() * 1000
        drift_ms = server_ts_ms - local_ms
        # No tocar el reloj si ya está prácticamente alineado (evita pisarlo en
        # cada heartbeat SYNC). La latencia LAN de un solo sentido es sub-ms,
        # despreciable frente al umbral y al delay base del sistema.
        if abs(drift_ms) < TIME_SYNC_THRESHOLD_MS:
            return

        epoch = server_ts_ms / 1000.0
        logger.info(
            f"⏰ Ajustando reloj al servidor (desfase {drift_ms/1000:.1f}s)"
        )
        try:
            process = await asyncio.create_subprocess_exec(
                'sudo', '-n', 'date', '-s', f'@{epoch:.3f}',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info("✅ Reloj sincronizado con el servidor")
            else:
                error_msg = stderr.decode().strip() if stderr else "sin detalles"
                logger.warning(f"⚠️  No se pudo ajustar el reloj: {error_msg}")

        except Exception as e:
            logger.error(f"❌ Error ajustando el reloj: {e}")
    
    async def process_message(self, line: str):
        """Procesa una línea recibida del servidor."""
        line = line.strip()
        if not line:
            return

        # RCONFIG lleva un JSON (con comas) tras la primera coma, así que se
        # trata ANTES del split. El sinte lo manda al conectar, antes que
        # cualquier NOTA: es la config autoritativa de esta robota.
        if line.startswith('RCONFIG,'):
            try:
                data = json.loads(line[len('RCONFIG,'):])
                self.config.load_from_dict(data)
                self.gpio_executor.ensure_pins(self.config.pines.keys())
                self.orchestrator.config = self.config
                logger.info(
                    f"📥 RCONFIG del sinte: {self.config.nombre} — "
                    f"{len(self.config.instruments)} notas, "
                    f"{len(self.config.pines)} pines")
            except (ValueError, KeyError) as e:
                logger.error(f"❌ RCONFIG inválido: {e}")
            return

        parts = line.split(',')
        if not parts:
            return

        msg_type = parts[0]
        
        try:
            if msg_type == 'CONFIG' and len(parts) >= 5:
                debug    = parts[2].lower() in ('1', 'true', 't', 'yes', 'y')
                ruido    = parts[3].lower() in ('1', 'true', 't', 'yes', 'y')
                pantalla = parts[4].lower() in ('1', 'true', 't', 'yes', 'y')
                logger.info(f"⚙️  CONFIG: debug={debug}, ruido={ruido}, pantalla={pantalla}")
                logging.getLogger().setLevel(logging.DEBUG if debug else logging.INFO)
                self.orchestrator.apply_config(debug, ruido, pantalla)
                self._write_status(debug, ruido, pantalla)
                
            elif msg_type == 'SYNC' and len(parts) >= 2:
                # El servidor envía su hora de pared (epoch ms) al conectar y en
                # heartbeats periódicos. La usamos para alinear el reloj local.
                server_ts_ms = int(parts[1])
                await self.sync_clock_to_server(server_ts_ms)
                
            elif msg_type == 'NOTA' and len(parts) >= 5:
                server_ts_ms = int(parts[1])
                note = int(parts[2])
                channel = int(parts[3])
                velocity = int(parts[4])
                
                logger.debug(f"🎵 NOTA {note} (canal {channel}, vel {velocity})")
                timing_log.log("NOTA_recv", note=note, ch=channel,
                               server_ts=server_ts_ms)  # LOG TEMPORAL
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

            elif msg_type == 'BPM' and len(parts) >= 3:
                server_ts_ms = int(parts[1])
                bpm = float(parts[2])
                self.orchestrator.handle_bpm(server_ts_ms, bpm)

            elif msg_type == 'CALIB' and len(parts) >= 6:
                robot = parts[2]
                if robot.lower() == self.config.nombre.lower():
                    pin = int(parts[3])
                    tiempo_ms = float(parts[4])
                    delay_ms = int(parts[5])
                    self.config.set_pin_override(pin, tiempo_ms / 1000.0, delay_ms)

            elif msg_type == 'CALTEST' and len(parts) >= 4:
                robot = parts[2]
                if robot.lower() == self.config.nombre.lower():
                    server_ts_ms = int(parts[1])
                    pin = int(parts[3])
                    timing_log.log("CALTEST_recv", pin=pin,
                                   server_ts=server_ts_ms)  # LOG TEMPORAL
                    # Se programa en el scheduler (ts + 1s - pin.delay), igual
                    # que una NOTA real, para que el timing de la calibración
                    # coincida con el de las canciones.
                    self.orchestrator.handle_caltest(server_ts_ms, pin)

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
        logger.info(f"Sincronización de reloj con el servidor: {'Activada' if ENABLE_TIME_SYNC else 'Desactivada'}")
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
                        # El reloj se sincroniza al recibir el primer SYNC del
                        # servidor (llega justo tras CONFIG, antes de cualquier
                        # evento). Ver sync_clock_to_server / process_message.
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
