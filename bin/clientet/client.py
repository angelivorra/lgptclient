#!/usr/bin/env python3
"""
Cliente TCP simplificado para servidor MIDI.

Funcionalidad básica:
1. Conectar al servidor TCP
2. Sincronizar tiempo con el servidor mediante mensajes SYNC
3. Recibir eventos y mostrarlos por pantalla

Protocolo de líneas (ASCII, terminadas en \n):
  CONFIG,<delay_ms>,<debug>,<ruido>,<pantalla>
  SYNC,<server_ts_ms>
  NOTA,<server_ts_ms>,<note>,<channel>,<velocity>
  CC,<server_ts_ms>,<value>,<channel>,<controller>
  START,<server_ts_ms>
  END,<server_ts_ms>
"""
import asyncio
import os
import time
import logging
from typing import Optional

# Configuración del servidor
SERVER_HOST = os.environ.get("SERVER_HOST", "192.168.0.2")
SERVER_PORT = int(os.environ.get("SERVER_PORT", "8888"))

# Configuración de sincronización NTP
ENABLE_NTP_SYNC = os.environ.get("ENABLE_NTP_SYNC", "0") == "1"

# Configuración de modo simulación GPIO
SIMULATE_GPIO = os.environ.get("SIMULATE_GPIO", "0") == "1"

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)-7s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("clientet")


class TimeSync:
    """Gestiona la sincronización de tiempo con el servidor mediante suavizado exponencial."""
    
    def __init__(self, alpha: float = 0.2):
        """
        Args:
            alpha: Factor de suavizado exponencial (0-1). Mayor valor = más reactivo.
        """
        self.alpha = alpha
        self.offset_ms: Optional[float] = None  # Diferencia: server_time - local_time
        self.samples = 0
    
    def update(self, server_ts_ms: int) -> tuple[int, float, bool]:
        """
        Actualiza el offset con un nuevo timestamp del servidor.
        
        Args:
            server_ts_ms: Timestamp del servidor en milisegundos
            
        Returns:
            tuple con (offset_muestra_actual, offset_filtrado, es_primera_muestra)
        """
        local_ts_ms = int(time.time() * 1000)
        sample_offset = server_ts_ms - local_ts_ms
        
        is_first = self.offset_ms is None
        
        if is_first:
            # Primera muestra: inicializar
            self.offset_ms = sample_offset
        else:
            # Suavizado exponencial: new_value = old_value + alpha * (sample - old_value)
            self.offset_ms += self.alpha * (sample_offset - self.offset_ms)
        
        self.samples += 1
        return sample_offset, self.offset_ms, is_first
    
    def get_offset(self) -> float:
        """Retorna el offset filtrado actual (0 si no hay muestras)."""
        return self.offset_ms if self.offset_ms is not None else 0.0


class SimpleTCPClient:
    """Cliente TCP simplificado que se conecta al servidor y procesa eventos."""
    
    def __init__(self):        
        self.delay_ms = 1000  # Delay fijo de 1 segundo
        self.debug = False
        self.ruido = False
        self.pantalla = False
    
    async def synchronize_system_time(self):
        """
        Sincroniza el reloj del sistema con el servidor usando ntpdate.
        Esto asegura que los timestamps del servidor y cliente están en el mismo marco temporal.
        """
        if not ENABLE_NTP_SYNC:
            logger.info("⏰ Sincronización NTP desactivada (ENABLE_NTP_SYNC=0)")
            return
        
        logger.info("⏰ Sincronizando reloj del sistema con el servidor...")
        
        try:
            # Ejecutar ntpdate en un proceso separado de forma asíncrona
            process = await asyncio.create_subprocess_exec(
                'sudo', 'ntpdate', '-u', SERVER_HOST,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info("✅ Reloj del sistema sincronizado exitosamente")
                if stdout:
                    # Mostrar la salida de ntpdate (muestra el ajuste realizado)
                    output = stdout.decode().strip()
                    logger.info(f"   {output}")
            else:
                error_msg = stderr.decode().strip() if stderr else "Sin detalles de error"
                logger.warning(f"⚠️  No se pudo sincronizar el reloj del sistema")
                logger.warning(f"   Error: {error_msg}")
                logger.warning(f"   Continuando sin sincronización (puede haber desfase temporal)")
                
        except FileNotFoundError:
            logger.error("❌ ntpdate no está instalado")
            logger.error("   Instala con: sudo apt-get install ntpdate")
            logger.warning("   Continuando sin sincronización (puede haber desfase temporal)")
            
        except Exception as e:
            logger.error(f"❌ Error inesperado sincronizando tiempo: {e}")
            logger.warning("   Continuando sin sincronización (puede haber desfase temporal)")
        
    def handle_config(self, parts: list[str]):
        """Procesa mensaje CONFIG del servidor."""
        if len(parts) < 5:
            logger.warning(f"CONFIG incompleto: {parts}")
            return
            
        try:
            # Ignoramos el delay del servidor, usamos siempre 1000ms
            self.debug = parts[2].lower() in ('1', 'true', 't', 'yes', 'y')
            self.ruido = parts[3].lower() in ('1', 'true', 't', 'yes', 'y')
            self.pantalla = parts[4].lower() in ('1', 'true', 't', 'yes', 'y')
            
            logger.info(f"⚙️  CONFIG recibida:")
            logger.info(f"   - Delay: {self.delay_ms} ms (fijo)")
            logger.info(f"   - Debug: {self.debug}")
            logger.info(f"   - Ruido: {self.ruido}")
            logger.info(f"   - Pantalla: {self.pantalla}")
            
        except ValueError as e:
            logger.error(f"Error parseando CONFIG: {e}")
    
    def handle_sync(self, parts: list[str]):
        """Procesa mensaje SYNC del servidor para sincronización de tiempo."""
        # Ignoramos los mensajes SYNC del servidor
        logger.debug(f"SYNC ignorado (no utilizado)")
    
    def handle_nota(self, parts: list[str]):
        """Procesa mensaje NOTA del servidor."""
        if len(parts) < 5:
            logger.warning(f"NOTA incompleta: {parts}")
            return
            
        try:
            server_ts_ms = int(parts[1])
            note = int(parts[2])
            channel = int(parts[3])
            velocity = int(parts[4])
            
            # Calcular tiempo local de ejecución (sin offset, solo delay fijo)
            local_execution_ms = server_ts_ms + self.delay_ms
            now_ms = int(time.time() * 1000)
            delta_ms = local_execution_ms - now_ms
            

            logger.debug(f"🎵 NOTA recibida:")
            logger.debug(f"   - Nota: {note}")
            logger.debug(f"   - Canal: {channel}")
            logger.debug(f"   - Velocidad: {velocity}")
            logger.debug(f"   - Timestamp servidor: {server_ts_ms} ms")
            logger.debug(f"   - Ejecutar en: {delta_ms:.1f} ms")

        except ValueError as e:
            logger.error(f"Error parseando NOTA: {e}")
    
    def handle_cc(self, parts: list[str]):
        """Procesa mensaje CC (Control Change) del servidor."""
        if len(parts) < 5:
            logger.warning(f"CC incompleto: {parts}")
            return
            
        try:
            server_ts_ms = int(parts[1])
            value = int(parts[2])
            channel = int(parts[3])
            controller = int(parts[4])
            
            # Calcular tiempo local de ejecución (sin offset, solo delay fijo)
            local_execution_ms = server_ts_ms + self.delay_ms
            now_ms = int(time.time() * 1000)
            delta_ms = local_execution_ms - now_ms

            logger.debug(f"🎛️  CC recibido:")
            logger.debug(f"   - Controlador: {controller}")
            logger.debug(f"   - Valor: {value}")
            logger.debug(f"   - Canal: {channel}")
            logger.debug(f"   - Timestamp servidor: {server_ts_ms} ms")
            logger.debug(f"   - Ejecutar en: {delta_ms:.1f} ms")
            
        except ValueError as e:
            logger.error(f"Error parseando CC: {e}")
    
    def handle_start(self, parts: list[str]):
        """Procesa mensaje START del servidor."""
        if len(parts) < 2:
            logger.warning(f"START incompleto: {parts}")
            return
            
        try:
            server_ts_ms = int(parts[1])
            logger.info(f"▶️  START recibido - Timestamp: {server_ts_ms} ms")
        except ValueError as e:
            logger.error(f"Error parseando START: {e}")
    
    def handle_end(self, parts: list[str]):
        """Procesa mensaje END del servidor."""
        if len(parts) < 2:
            logger.warning(f"END incompleto: {parts}")
            return
            
        try:
            server_ts_ms = int(parts[1])
            logger.info(f"⏹️  END recibido - Timestamp: {server_ts_ms} ms")
        except ValueError as e:
            logger.error(f"Error parseando END: {e}")
    
    async def process_message(self, line: str):
        """Procesa una línea recibida del servidor."""
        line = line.strip()
        if not line:
            return
            
        parts = line.split(',')
        if not parts:
            return
            
        msg_type = parts[0]
        
        # Despachar según tipo de mensaje
        handlers = {
            'CONFIG': self.handle_config,
            'SYNC': self.handle_sync,
            'NOTA': self.handle_nota,
            'CC': self.handle_cc,
            'START': self.handle_start,
            'END': self.handle_end,
        }
        
        handler = handlers.get(msg_type)
        if handler:
            handler(parts)
        else:
            logger.debug(f"Mensaje desconocido: {line}")
    
    async def run(self):
        """Loop principal del cliente."""
        logger.info("=" * 60)
        logger.info("Cliente TCP Simple - Iniciando")
        logger.info("=" * 60)
        logger.info(f"Servidor: {SERVER_HOST}:{SERVER_PORT}")
        logger.info(f"Sincronización NTP: {'Activada' if ENABLE_NTP_SYNC else 'Desactivada'}")
        logger.info(f"Modo GPIO: {'Simulación' if SIMULATE_GPIO else 'Real'}")
        logger.info("")
        
        while True:
            try:
                logger.info(f"🔌 Conectando a {SERVER_HOST}:{SERVER_PORT}...")
                reader, writer = await asyncio.open_connection(SERVER_HOST, SERVER_PORT)
                logger.info("✅ Conectado al servidor")
                logger.info("")
                
                try:
                    # Sincronizar tiempo del sistema con el servidor ANTES de recibir eventos
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
                    
            except Exception as e:
                logger.error(f"❌ Error de conexión: {e}")
                
            # Esperar antes de reintentar
            logger.info("")
            logger.info("⏳ Reintentando conexión en 3 segundos...")
            logger.info("")
            await asyncio.sleep(3)


async def main():
    """Punto de entrada principal."""
    client = SimpleTCPClient()
    try:
        await client.run()
    except KeyboardInterrupt:
        logger.info("")
        logger.info("=" * 60)
        logger.info("👋 Cliente detenido por el usuario")
        logger.info("=" * 60)


if __name__ == '__main__':
    asyncio.run(main())
