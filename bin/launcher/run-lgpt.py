#!/usr/bin/env python3
"""Launcher sencillo para LGPT sobre JACK.

La secuencia es:
    1. Mata restos de jackd / alsa_in / lgpt.
    2. Arranca jackd con parámetros fijos y espera a que quede listo.
    3. Arranca alsa_in sobre la tarjeta loopback y espera los puertos.
    4. Conecta LGPT -> system playback.
    5. Lanza LGPT y lo reinicia si se cierra.

La configuración puede ajustarse vía variables de entorno
(LGPT_JACK_RATE, LGPT_JACK_PERIOD, etc.).
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional, Tuple

LGPT_BIN = "/home/angel/lgptclient/lgpt/bin/lgpt.rpi-exe"
DELAY_BUFFER_BIN = "/home/angel/lgptclient/bin/launcher/jack_delay_buffer.py"
LOG_FILE = "/home/angel/lgpt.log"
EXEC_LOG_FILE = "/home/angel/lgpt.exec.log"

# Si hay delay configurado, las conexiones van a través del buffer de delay
# Si no hay delay, conexión directa a system:playback
CONNECTIONS_WITH_DELAY: List[Tuple[str, str]] = [
    ("LGPT:capture_1", "delay_buffer:input_L"),
    ("LGPT:capture_2", "delay_buffer:input_R"),
    ("delay_buffer:output_L", "system:playback_1"),
    ("delay_buffer:output_R", "system:playback_2"),
]

CONNECTIONS_DIRECT: List[Tuple[str, str]] = [
    ("LGPT:capture_1", "system:playback_1"),
    ("LGPT:capture_2", "system:playback_2"),
]

JACK_ENV = {
    "JACK_NO_AUDIO_RESERVATION": "1"
}

PROCESSES_TO_CLEAN = ["jackd", "alsa_in", "lgpt.rpi-exe", "jack_delay_buffer.py"]
STOP_EVENT = threading.Event()

# Variables de control para debugging
ARRANCAR_JACKD = os.environ.get("LGPT_ARRANCAR_JACKD", "1") == "1"
ARRANCAR_ALSA_IN = os.environ.get("LGPT_ARRANCAR_ALSA_IN", "1") == "1"
ARRANCAR_LGPT = os.environ.get("LGPT_ARRANCAR_LGPT", "1") == "1"
AUDIO_DELAY_SECONDS = float(os.environ.get("LGPT_AUDIO_DELAY", "1.0"))


def setup_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s: %(message)s",
        level=logging.INFO,
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stdout),
        ],
    )


@dataclass
class AudioConfig:
    jack_rate: str
    jack_period: str
    jack_nperiods: str
    hw_playback: str
    loopback_capture_hw: str
    loopback_playback_card: str
    loopback_playback_device: str
    loopback_playback_subdevice: str
    jack_timeout: float
    alsa_port_timeout: float
    retry_delay: float
    max_restarts: int
    alsa_in_delay_samples: int


def _env_or(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value else default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        logging.warning("Valor inválido para %s; usando %.2f", name, default)
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logging.warning("Valor inválido para %s; usando %d", name, default)
        return default


def load_config() -> AudioConfig:
    return AudioConfig(
        jack_rate=_env_or("LGPT_JACK_RATE", "44100"),
        jack_period=_env_or("LGPT_JACK_PERIOD", "512"),
        jack_nperiods=_env_or("LGPT_JACK_NPERIODS", "3"),
        hw_playback=_env_or("LGPT_HW_PLAYBACK", "hw:IQaudIODAC"),
        loopback_capture_hw=_env_or("LGPT_HW_LOOPBACK", "hw:2,1,0"),
        loopback_playback_card=_env_or("LGPT_LOOPBACK_CARD", "2"),
        loopback_playback_device=_env_or("LGPT_LOOPBACK_DEVICE", "0"),
        loopback_playback_subdevice=_env_or("LGPT_LOOPBACK_SUBDEVICE", "0"),
        jack_timeout=_env_float("LGPT_JACK_START_TIMEOUT", 10.0),
        alsa_port_timeout=_env_float("LGPT_ALSA_PORT_TIMEOUT", 10.0),
        retry_delay=_env_float("LGPT_RETRY_DELAY", 3.0),
        max_restarts=_env_int("LGPT_MAX_RESTARTS", -1),
        alsa_in_delay_samples=_env_int("LGPT_ALSA_IN_DELAY", 44100),  # 1 segundo @ 44.1kHz
    )


class TailCapture:
    """Lee un stream en un hilo y guarda sólo las últimas líneas."""

    def __init__(self, stream, label: str, max_lines: int = 80):
        self._stream = stream
        self._label = label
        self._lines: Deque[str] = deque(maxlen=max_lines)
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if not self._stream:
            return

        def _reader() -> None:
            for raw in iter(self._stream.readline, ""):
                if not raw:
                    break
                line = raw.rstrip()
                if line:
                    self._lines.append(line)
                    logging.debug("%s: %s", self._label, line)

        self._thread = threading.Thread(target=_reader, daemon=True)
        self._thread.start()

    def tail(self) -> List[str]:
        return list(self._lines)


class AudioStack:
    def __init__(self, config: AudioConfig):
        self.config = config
        self.jackd: Optional[subprocess.Popen] = None
        self.alsa_in: Optional[subprocess.Popen] = None
        self.delay_buffer: Optional[subprocess.Popen] = None
        self.jack_stdout: Optional[TailCapture] = None
        self.jack_stderr: Optional[TailCapture] = None

    def start(self) -> bool:
        # Arrancar jackd si está habilitado
        if ARRANCAR_JACKD:
            jack_result = start_jackd(self.config)
            if not jack_result:
                return False
            self.jackd, self.jack_stdout, self.jack_stderr = jack_result

            # Esperar más tiempo en boot para que jackd se estabilice completamente
            # Durante el arranque del sistema, puede tardar más
            stabilization_time = 5.0
            logging.info("Esperando %.1fs para estabilización de jackd...", stabilization_time)
            time.sleep(stabilization_time)
        else:
            logging.warning("ARRANCAR_JACKD=False - Saltando inicio de jackd (debe estar corriendo externamente)")
            # Verificar que jackd esté corriendo
            if subprocess.run(["jack_lsp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
                logging.error("jackd no está corriendo y ARRANCAR_JACKD=False")
                return False
            logging.info("jackd externo detectado y operativo")

        # Arrancar alsa_in si está habilitado
        if ARRANCAR_ALSA_IN:
            alsa_proc = start_alsa_in(self.config)
            if not alsa_proc:
                logging.error("No se pudo iniciar alsa_in")
                if ARRANCAR_JACKD:
                    logging.error("Deteniendo jackd")
                    terminate_process(self.jackd, "jackd")
                    self.jackd = None
                return False
            self.alsa_in = alsa_proc
        else:
            logging.warning("ARRANCAR_ALSA_IN=False - Saltando inicio de alsa_in")
            # Verificar que los puertos LGPT existan
            if not jack_ports_present():
                logging.error("Puertos LGPT no encontrados y ARRANCAR_ALSA_IN=False")
                return False
            logging.info("Puertos LGPT detectados externamente")

        # Arrancar buffer de delay si está configurado
        connections = CONNECTIONS_DIRECT
        if AUDIO_DELAY_SECONDS > 0:
            delay_proc = start_delay_buffer(AUDIO_DELAY_SECONDS)
            if not delay_proc:
                logging.error("No se pudo iniciar buffer de delay")
                if ARRANCAR_ALSA_IN:
                    terminate_process(self.alsa_in, "alsa_in")
                if ARRANCAR_JACKD:
                    terminate_process(self.jackd, "jackd")
                return False
            self.delay_buffer = delay_proc
            connections = CONNECTIONS_WITH_DELAY
        else:
            logging.info("Sin delay de audio (LGPT_AUDIO_DELAY=0)")

        # Conectar puertos
        connect_ports(connections)
        return True

    def stop(self) -> None:
        if self.delay_buffer:
            terminate_process(self.delay_buffer, "delay_buffer")
        if ARRANCAR_ALSA_IN:
            terminate_process(self.alsa_in, "alsa_in")
        if ARRANCAR_JACKD:
            terminate_process(self.jackd, "jackd")
        self.delay_buffer = None
        self.alsa_in = None
        self.jackd = None
        self.jack_stdout = None
        self.jack_stderr = None


@dataclass
class RuntimeState:
    stack: Optional[AudioStack] = None
    lgpt_process: Optional[subprocess.Popen] = None


RUNTIME_STATE = RuntimeState()


def clean_jack_environment() -> None:
    """Limpia completamente el entorno de JACK antes de iniciar."""
    logging.info("Limpiando entorno JACK...")
    
    # 1. Matar procesos con pkill como respaldo
    for cmd in [["pkill", "-9", "jackd"], ["pkill", "-9", "alsa_in"]]:
        try:
            subprocess.run(cmd, check=False, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    
    time.sleep(0.5)
    
    # 2. Limpiar sockets y directorios temporales
    uid = os.getuid()
    jack_locations = [
        f"/dev/shm/jack-{uid}",
        f"/tmp/jack-{uid}",
        f"/dev/shm/jack_default_{uid}",
        f"/tmp/jack_default_{uid}",
        "/dev/shm/jack-shm-registry",
        "/var/run/jack",
    ]
    
    # Si somos root (uid 0), también limpiar directorios comunes de otros usuarios
    if uid == 0:
        try:
            import glob
            for pattern in ["/dev/shm/jack-*", "/tmp/jack-*", "/dev/shm/jack_*"]:
                for path in glob.glob(pattern):
                    if path not in jack_locations:
                        jack_locations.append(path)
        except Exception:
            pass
    
    for location in jack_locations:
        if os.path.exists(location):
            try:
                if os.path.isdir(location):
                    shutil.rmtree(location)
                else:
                    os.remove(location)
                logging.info("Eliminado: %s", location)
            except Exception as exc:
                logging.warning("No se pudo eliminar %s: %s", location, exc)
    
    # 3. Pequeña espera para que el sistema libere recursos
    time.sleep(0.3)


def kill_processes(names: List[str]) -> None:
    try:
        ps_out = subprocess.check_output(["ps", "-eo", "pid,comm,args"], text=True, stderr=subprocess.DEVNULL)
    except Exception as exc:
        logging.warning("No se pudo listar procesos para limpiar: %s", exc)
        return

    targets: List[Tuple[int, str]] = []
    for line in ps_out.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 2:
            continue
        pid_str, comm = parts[0], parts[1]
        args = parts[2] if len(parts) > 2 else ""
        try:
            pid = int(pid_str)
        except ValueError:
            continue
        if pid == os.getpid():
            continue
        if any(name in comm or name in args for name in names):
            targets.append((pid, comm))

    if not targets:
        logging.info("Pre-clean: no se encontraron procesos previos de %s", "/".join(names))
        return

    logging.info("Pre-clean: terminando %d procesos previos", len(targets))
    for pid, comm in targets:
        try:
            logging.info("Enviando SIGTERM a %s (pid=%d)", comm, pid)
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        except PermissionError:
            logging.warning("Sin permisos para terminar %s (pid=%d)", comm, pid)
        except Exception as exc:
            logging.error("Error terminando %s (pid=%d): %s", comm, pid, exc)

    deadline = time.time() + 2.0
    while time.time() < deadline:
        alive = [pid for pid, _ in targets if os.path.exists(f"/proc/{pid}")]
        if not alive:
            break
        time.sleep(0.1)

    for pid, comm in targets:
        if os.path.exists(f"/proc/{pid}"):
            try:
                logging.info("Forzando SIGKILL a %s (pid=%d)", comm, pid)
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass

    time.sleep(0.3)
    logging.info("Pre-clean completado")


def terminate_process(proc: Optional[subprocess.Popen], name: str, timeout: float = 2.0) -> None:
    if proc is None:
        return
    if proc.poll() is not None:
        return
    try:
        logging.info("Deteniendo %s...", name)
        proc.terminate()
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        logging.warning("%s no respondió a SIGTERM; enviando SIGKILL", name)
        try:
            proc.kill()
            proc.wait(timeout=1.0)
        except Exception as exc:
            logging.error("No se pudo finalizar %s: %s", name, exc)
    except Exception as exc:
        logging.error("Error deteniendo %s: %s", name, exc)


def jack_ports_present() -> bool:
    try:
        result = subprocess.run(["jack_lsp"], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        logging.error("jack_lsp no disponible; no se puede comprobar puertos")
        return False
    if result.returncode != 0:
        return False
    ports = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    return {"LGPT:capture_1", "LGPT:capture_2"}.issubset(ports)


def verify_alsa_device(device: str, capture=True) -> bool:
    """Verifica que un dispositivo ALSA esté disponible.
    
    Args:
        device: El dispositivo ALSA (ej: hw:2,1,0)
        capture: True para verificar dispositivo de captura, False para playback
    """
    cmd = ["arecord", "-l"] if capture else ["aplay", "-l"]
    device_type = "captura" if capture else "reproducción"
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=2.0
        )
        
        if device in result.stdout:
            logging.info("Dispositivo ALSA %s (%s) encontrado", device, device_type)
            return True
        
        # Verificar formato hw:card,device,subdevice
        if "hw:" in device:
            parts = device.replace("hw:", "").split(",")
            if len(parts) >= 2:
                card, dev = parts[0], parts[1]
                # Buscar "card X:" y "device Y:"
                if f"card {card}:" in result.stdout and f"device {dev}:" in result.stdout:
                    logging.info("Dispositivo %s encontrado (card=%s, device=%s)", device, card, dev)
                    return True
        
        logging.warning("Dispositivo %s no encontrado en %s, pero intentando de todas formas", device, " ".join(cmd))
        return True  # Intentar de todas formas
                
    except Exception as exc:
        logging.warning("No se pudo verificar dispositivo ALSA %s: %s", device, exc)
    
    return True  # Asumir que está disponible si no podemos verificar


def wait_for_jackd(proc: subprocess.Popen, config: AudioConfig, jack_env: dict) -> bool:
    jack_wait_bin = shutil.which("jack_wait")
    if jack_wait_bin:
        try:
            subprocess.run([jack_wait_bin, "-w"], env=jack_env, check=True, timeout=config.jack_timeout)
            # Espera adicional después de jack_wait para garantizar estabilidad
            time.sleep(1.0)
            return True
        except subprocess.TimeoutExpired:
            logging.warning("jack_wait no confirmó jackd en %.1fs", config.jack_timeout)
        except subprocess.CalledProcessError as exc:
            logging.warning("jack_wait terminó con código %s; se usará comprobación manual", exc.returncode)
        except Exception as exc:
            logging.warning("No se pudo ejecutar jack_wait: %s", exc)

    deadline = time.time() + config.jack_timeout
    consecutive_success = 0
    while time.time() < deadline:
        if proc.poll() is not None:
            logging.error("jackd terminó prematuramente (rc=%s)", proc.returncode)
            return False
        
        # Verificar que jack_lsp funcione consistentemente
        result = subprocess.run(["jack_lsp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=jack_env)
        if result.returncode == 0:
            consecutive_success += 1
            if consecutive_success >= 3:  # 3 checks exitosos seguidos
                logging.info("jackd confirmado estable después de %d verificaciones", consecutive_success)
                time.sleep(0.5)  # Espera adicional para garantizar estabilidad total
                return True
        else:
            consecutive_success = 0
            
        if STOP_EVENT.wait(0.2):
            break
    return False


def start_jackd(config: AudioConfig) -> Optional[Tuple[subprocess.Popen, TailCapture, TailCapture]]:
    if not shutil.which("jackd"):
        logging.error("jackd no encontrado en PATH")
        return None

    cmd = [
        "jackd",
        "-R",
        "-P70",
        "-d",
        "alsa",
        "-d",
        config.hw_playback,
        "-P",
        "-r",
        config.jack_rate,
        "-p",
        config.jack_period,
        "-n",
        config.jack_nperiods,
        "-S",
    ]

    logging.info(
        "Configuración JACK -> rate=%s period=%s nperiods=%s hw=%s loopback=%s",
        config.jack_rate,
        config.jack_period,
        config.jack_nperiods,
        config.hw_playback,
        config.loopback_capture_hw,
    )
    logging.info("Lanzando jackd: %s", " ".join(cmd))

    env = os.environ.copy()
    env.update(JACK_ENV)

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            env=env,
        )
    except Exception as exc:
        logging.error("Error lanzando jackd: %s", exc)
        return None

    stdout_tail = TailCapture(proc.stdout, "jackd stdout")
    stderr_tail = TailCapture(proc.stderr, "jackd stderr")
    stdout_tail.start()
    stderr_tail.start()

    if wait_for_jackd(proc, config, env):
        logging.info("jackd operativo")
        return proc, stdout_tail, stderr_tail

    logging.error("No se confirmó arranque estable de jackd dentro de %.1fs", config.jack_timeout)
    if stdout_tail.tail():
        logging.error("jackd STDOUT tail:\n%s", "\n".join(stdout_tail.tail()))
    if stderr_tail.tail():
        logging.error("jackd STDERR tail:\n%s", "\n".join(stderr_tail.tail()))
    terminate_process(proc, "jackd")
    return None


def start_delay_buffer(delay_seconds: float) -> Optional[subprocess.Popen]:
    """Inicia el cliente JACK de buffer de delay."""
    if not os.path.exists(DELAY_BUFFER_BIN):
        logging.error("Buffer de delay no encontrado en %s", DELAY_BUFFER_BIN)
        return None
    
    python_bin = sys.executable
    cmd = [python_bin, "-u", DELAY_BUFFER_BIN, str(delay_seconds), "delay_buffer"]
    
    logging.info("Iniciando buffer de delay de %.2fs...", delay_seconds)
    logging.info("Comando: %s", " ".join(cmd))
    
    # Crear archivo de log para el delay buffer (con timestamp para debug)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_file_path = f"/tmp/jack_delay_buffer_{timestamp}.log"
    # También mantener un symlink al último log
    log_file_link = "/tmp/jack_delay_buffer_latest.log"
    
    # Preparar el entorno: heredar variables de JACK del entorno actual
    env = os.environ.copy()
    
    try:
        log_file = open(log_file_path, "w", buffering=1)  # line buffering
        proc = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            start_new_session=True,
        )
        logging.info("Proceso delay_buffer iniciado (PID: %d, log: %s)", proc.pid, log_file_path)
        
        # Crear symlink al último log para fácil acceso
        try:
            if os.path.exists(log_file_link) or os.path.islink(log_file_link):
                os.remove(log_file_link)
            os.symlink(log_file_path, log_file_link)
        except Exception:
            pass  # No crítico si falla
            
    except Exception as exc:
        logging.error("Error lanzando buffer de delay: %s", exc)
        return None
    
    # Esperar a que el cliente JACK se registre y los puertos estén disponibles
    timeout_seconds = 20.0  # Aumentado a 20 segundos para boot lento
    deadline = time.time() + timeout_seconds
    start_time = time.time()
    checks = 0
    last_log_time = start_time
    
    while time.time() < deadline:
        checks += 1
        elapsed = time.time() - start_time
        
        # Log de progreso cada 3 segundos
        if time.time() - last_log_time >= 3.0:
            logging.info("Esperando delay_buffer... (%.1fs, %d checks)", elapsed, checks)
            last_log_time = time.time()
        
        # Verificar si el proceso sigue vivo
        if proc.poll() is not None:
            elapsed_final = time.time() - start_time
            logging.error("Buffer de delay terminó prematuramente después de %.1fs (código: %s)", elapsed_final, proc.returncode)
            try:
                log_file.flush()
                log_file.close()
                with open(log_file_path, "r") as f:
                    log_content = f.read()
                if log_content:
                    logging.error("Log del delay buffer:\n%s", log_content)
                else:
                    logging.error("Log del delay buffer está vacío")
            except Exception as e:
                logging.error("No se pudo leer el log: %s", e)
            return None
        
        # Verificar que los puertos del delay buffer existan
        try:
            result = subprocess.run(["jack_lsp"], capture_output=True, text=True, check=False, timeout=1.0)
            if result.returncode == 0:
                ports = result.stdout
                if "delay_buffer:input_L" in ports and "delay_buffer:output_L" in ports:
                    elapsed_final = time.time() - start_time
                    logging.info("✓ Buffer de delay operativo (%.1fs, %d checks)", elapsed_final, checks)
                    return proc
            else:
                if checks % 10 == 0:  # Log cada 10 checks
                    logging.debug("jack_lsp falló (check %d): rc=%d", checks, result.returncode)
        except subprocess.TimeoutExpired:
            logging.warning("jack_lsp timeout en check %d", checks)
        except Exception as e:
            if checks % 10 == 0:  # Log cada 10 checks
                logging.debug("Error ejecutando jack_lsp (check %d): %s", checks, e)
        
        time.sleep(0.2)
    
    # Timeout: verificar el estado final
    elapsed_final = time.time() - start_time
    logging.error("⏱ Timeout esperando puertos del buffer de delay (%.1fs, %d checks)", elapsed_final, checks)
    logging.error("Proceso delay_buffer PID=%d, poll=%s", proc.pid, proc.poll())
    
    # Intentar leer el log antes de terminar el proceso
    try:
        log_file.flush()
        log_file.close()
        with open(log_file_path, "r") as f:
            log_content = f.read()
        if log_content:
            logging.error("Log del delay buffer en timeout:\n%s", log_content)
        else:
            logging.error("⚠ Log del delay buffer está vacío después del timeout")
            logging.error("Esto sugiere que el proceso no pudo escribir nada (posible problema de permisos o crash inmediato)")
    except Exception as e:
        logging.error("No se pudo leer el log después del timeout: %s", e)
    
    # Verificar estado de JACK antes de terminar
    try:
        result = subprocess.run(["jack_lsp"], capture_output=True, text=True, check=False, timeout=2.0)
        if result.returncode == 0:
            logging.error("Puertos JACK disponibles en timeout:\n%s", result.stdout[:500])
        else:
            logging.error("jack_lsp falló en timeout: rc=%d", result.returncode)
    except Exception as e:
        logging.error("No se pudo ejecutar jack_lsp en timeout: %s", e)
    
    terminate_process(proc, "delay_buffer")
    return None


def start_alsa_in(config: AudioConfig) -> Optional[subprocess.Popen]:
    if not shutil.which("alsa_in"):
        logging.error("alsa_in no encontrado en PATH")
        return None

    # Verificar dispositivo loopback (es un dispositivo de captura)
    if not verify_alsa_device(config.loopback_capture_hw, capture=True):
        logging.error("Dispositivo loopback %s no disponible", config.loopback_capture_hw)
        return None

    cmd = [
        "alsa_in",
        "-j",
        "LGPT",
        "-d",
        config.loopback_capture_hw,
        "-r",
        config.jack_rate,
        "-c",
        "2",
        "-p",
        config.jack_period,
        "-n",
        config.jack_nperiods,
        "-q",
        "1",
    ]
    
    logging.info("Lanzando alsa_in: %s", " ".join(cmd))

    env = os.environ.copy()
    env.update(JACK_ENV)

    # Verificar que jackd esté respondiendo antes de lanzar alsa_in
    try:
        result = subprocess.run(["jack_lsp"], capture_output=True, text=True, env=env, timeout=2.0)
        if result.returncode != 0:
            logging.error("jackd no responde a jack_lsp antes de iniciar alsa_in")
            return None
        logging.info("jackd confirmado activo antes de iniciar alsa_in")
    except Exception as exc:
        logging.error("No se pudo verificar jackd antes de alsa_in: %s", exc)
        return None

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            env=env,
        )
    except Exception as exc:
        logging.error("Error lanzando alsa_in: %s", exc)
        return None

    # Capturar output para debugging
    stdout_capture = TailCapture(proc.stdout, "alsa_in stdout")
    stderr_capture = TailCapture(proc.stderr, "alsa_in stderr")
    stdout_capture.start()
    stderr_capture.start()

    start_time = time.time()
    check_count = 0
    while time.time() - start_time < config.alsa_port_timeout:
        check_count += 1
        
        if proc.poll() is not None:
            logging.error("alsa_in terminó prematuramente (rc=%s)", proc.returncode)
            if stdout_capture.tail():
                logging.error("alsa_in STDOUT:\n%s", "\n".join(stdout_capture.tail()))
            if stderr_capture.tail():
                logging.error("alsa_in STDERR:\n%s", "\n".join(stderr_capture.tail()))
            return None
            
        if jack_ports_present():
            logging.info("Puertos LGPT:capture_* disponibles después de %d checks", check_count)
            return proc
            
        if check_count % 10 == 0:  # Log cada 2 segundos
            logging.info("Esperando puertos LGPT... (%.1fs transcurridos)", time.time() - start_time)
            
        if STOP_EVENT.wait(0.2):
            break

    logging.error("Timeout esperando puertos de alsa_in (%.1fs, %d checks)", config.alsa_port_timeout, check_count)
    
    # Verificar si el proceso sigue corriendo
    if proc.poll() is None:
        logging.error("alsa_in SIGUE CORRIENDO pero no creó puertos")
    else:
        logging.error("alsa_in YA TERMINÓ con código %s", proc.returncode)
    
    if stdout_capture.tail():
        logging.error("alsa_in STDOUT:\n%s", "\n".join(stdout_capture.tail()))
    else:
        logging.error("alsa_in STDOUT: (vacío)")
        
    if stderr_capture.tail():
        logging.error("alsa_in STDERR:\n%s", "\n".join(stderr_capture.tail()))
    else:
        logging.error("alsa_in STDERR: (vacío)")
    
    terminate_process(proc, "alsa_in")
    return None


def connect_ports(pairs: List[Tuple[str, str]]) -> None:
    existing: set[Tuple[str, str]] = set()
    try:
        result = subprocess.run(["jack_lsp", "-c"], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        logging.error("jack_lsp no disponible; no se pueden conectar puertos automáticamente")
        return

    if result.returncode == 0:
        current: Optional[str] = None
        for line in result.stdout.splitlines():
            if line.startswith("    "):
                if current:
                    existing.add((current, line.strip()))
            else:
                current = line.strip()

    for src, dst in pairs:
        if (src, dst) in existing:
            continue
        try:
            subprocess.run(["jack_connect", src, dst], check=True)
            logging.info("Conectado %s -> %s", src, dst)
        except subprocess.CalledProcessError as exc:
            logging.warning("No se pudo conectar %s -> %s (%s)", src, dst, exc)


def start_lgpt(config: AudioConfig) -> Optional[subprocess.Popen]:
    if not os.path.exists(LGPT_BIN):
        logging.critical("No se encontró el binario de LGPT en %s", LGPT_BIN)
        return None

    env = os.environ.copy()
    logging.info("Lanzando LGPT...")

    try:
        proc = subprocess.Popen(
            [LGPT_BIN],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=False,
            env=env,
        )
    except PermissionError:
        logging.critical("Permiso denegado al ejecutar %s. Revisa chmod +x.", LGPT_BIN)
        return None
    except FileNotFoundError:
        logging.critical("No se pudo ejecutar %s. Verifica la ruta y dependencias.", LGPT_BIN)
        return None
    except Exception as exc:
        logging.critical("Error lanzando LGPT: %s", exc)
        return None

    return proc


def collect_process_output(proc: subprocess.Popen) -> Tuple[List[str], List[str], int]:
    stdout_lines: List[str] = []
    stderr_lines: List[str] = []

    def _reader(stream, bucket: List[str], label: str) -> None:
        for raw in iter(stream.readline, ""):
            if not raw:
                break
            bucket.append(raw)
            logging.debug("%s: %s", label, raw.rstrip())

    threads = []
    if proc.stdout:
        threads.append(threading.Thread(target=_reader, args=(proc.stdout, stdout_lines, "LGPT OUT"), daemon=True))
    if proc.stderr:
        threads.append(threading.Thread(target=_reader, args=(proc.stderr, stderr_lines, "LGPT ERR"), daemon=True))

    for thread in threads:
        thread.start()

    proc.wait()

    for thread in threads:
        thread.join(timeout=0.2)

    code = proc.returncode if proc.returncode is not None else 0
    return stdout_lines, stderr_lines, code


def write_exec_log(stdout_lines: List[str], stderr_lines: List[str], code: int) -> None:
    try:
        with open(EXEC_LOG_FILE, "w", encoding="utf-8") as log_file:
            log_file.write("=== OUTPUT ===\n")
            log_file.writelines(stdout_lines)
            log_file.write("\n=== ERRORS ===\n")
            log_file.writelines(stderr_lines)
            log_file.write(f"\nEXIT CODE: {code}\n")
    except Exception as exc:
        logging.error("No se pudo escribir EXEC_LOG_FILE: %s", exc)


def run_lgpt_loop(config: AudioConfig, stack: 'AudioStack') -> None:
    restarts = 0
    max_restarts = config.max_restarts

    while not STOP_EVENT.is_set():
        proc = start_lgpt(config)
        if not proc:
            return

        RUNTIME_STATE.lgpt_process = proc
        stdout_lines, stderr_lines, code = collect_process_output(proc)
        RUNTIME_STATE.lgpt_process = None

        write_exec_log(stdout_lines, stderr_lines, code)

        if STOP_EVENT.is_set():
            logging.info("Salida solicitada; no se relanza LGPT.")
            break

        restarts += 1
        logging.info("LGPT terminó (code=%s) -> reinicio #%d en %.1fs", code, restarts, config.retry_delay)
        if max_restarts >= 0 and restarts > max_restarts:
            logging.info("Alcanzado LGPT_MAX_RESTARTS (%d). Fin del loop.", max_restarts)
            break

        if STOP_EVENT.wait(config.retry_delay):
            logging.info("Salida solicitada durante la espera de reinicio.")
            break
        
        # Reiniciar pila de audio antes del siguiente intento
        logging.info("Reiniciando pila de audio antes de relanzar LGPT...")
        stack.stop()
        time.sleep(1.0)  # Esperar un poco para que los procesos terminen completamente
        
        if not stack.start():
            logging.error("No se pudo reiniciar la pila de audio; abortando loop de LGPT")
            break


def signal_handler(signum, _frame) -> None:
    logging.info("Recibida señal %s; iniciando apagado...", signum)
    STOP_EVENT.set()
    if RUNTIME_STATE.lgpt_process:
        terminate_process(RUNTIME_STATE.lgpt_process, "LGPT")
    if RUNTIME_STATE.stack:
        RUNTIME_STATE.stack.stop()


def main() -> None:
    setup_logging()
    config = load_config()

    # Mostrar configuración de arranque
    logging.info("=== Configuración de arranque ===")
    logging.info("ARRANCAR_JACKD: %s", ARRANCAR_JACKD)
    logging.info("ARRANCAR_ALSA_IN: %s", ARRANCAR_ALSA_IN)
    logging.info("ARRANCAR_LGPT: %s", ARRANCAR_LGPT)
    logging.info("================================")

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    kill_processes(PROCESSES_TO_CLEAN)
    clean_jack_environment()

    stack = AudioStack(config)
    RUNTIME_STATE.stack = stack

    if not stack.start():
        logging.error("Fallo preparando pila de audio; abortando")
        stack.stop()
        return

    try:
        if ARRANCAR_LGPT:
            run_lgpt_loop(config, stack)
        else:
            logging.warning("ARRANCAR_LGPT=False - No se iniciará LGPT, esperando señal de terminación...")
            STOP_EVENT.wait()
    finally:
        stack.stop()
        logging.info("Cleanup final completado (jackd/alsa_in/lgpt detenidos)")


if __name__ == "__main__":
    main()