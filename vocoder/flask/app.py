#!/usr/bin/env python3
"""Pivocoder Flask Web Interface.

Gestiona Carla en modo headless y expone una interfaz web para controlar
el vocoder: cambio de presets, estado de JACK/Carla y reinicio del sistema.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, render_template

from tcp_client import start_tcp_client

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

PRESET_DIR = Path("/home/patch/pivocoder/prod")
FIXED_PRESET = "template01.carxp"
CARLA_RUNNER = Path(__file__).resolve().parent / "carla_runner.py"
CARLA_ENV = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Estado global de Carla
# ---------------------------------------------------------------------------

_carla_process: Optional[subprocess.Popen] = None
_current_preset: Optional[str] = None
_carla_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Gestión de Carla
# ---------------------------------------------------------------------------

def _stop_carla() -> None:
    """Detiene el proceso de Carla si está corriendo. Debe llamarse con _carla_lock."""
    global _carla_process, _current_preset
    if _carla_process is None:
        return
    if _carla_process.poll() is None:
        _carla_process.terminate()
        try:
            _carla_process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            _carla_process.kill()
            _carla_process.wait()
    _carla_process = None
    _current_preset = None


def _start_carla(preset_name: str) -> None:
    """Lanza Carla con el preset indicado. Debe llamarse con _carla_lock adquirido."""
    global _carla_process, _current_preset
    preset_path = PRESET_DIR / preset_name
    if not preset_path.exists():
        raise FileNotFoundError(f"Preset no encontrado: {preset_path}")
    _stop_carla()
    _carla_process = subprocess.Popen(
        [sys.executable, str(CARLA_RUNNER), str(preset_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=CARLA_ENV,
    )
    _current_preset = preset_name


def is_jack_running() -> bool:
    """Comprueba si jackd está activo usando jack_lsp (más fiable que jack_control)."""
    try:
        result = subprocess.run(
            ["jack_lsp"],
            capture_output=True,
            timeout=2,
        )
        return result.returncode == 0
    except Exception:
        return False


def is_carla_running() -> bool:
    """Comprueba si el proceso de Carla gestionado está vivo."""
    return _carla_process is not None and _carla_process.poll() is None


_CARLA_BACKOFF_INITIAL = 2
_CARLA_BACKOFF_MAX = 30


def _carla_supervisor() -> None:
    """Arranca Carla y la reinicia con backoff exponencial si muere."""
    global _carla_process
    time.sleep(1)  # pequeña espera para que Flask esté listo
    backoff = _CARLA_BACKOFF_INITIAL
    while True:
        with _carla_lock:
            running = _carla_process is not None and _carla_process.poll() is None
            if not running:
                try:
                    _start_carla(FIXED_PRESET)
                    print(f"[pivocoder] Carla arrancada con '{FIXED_PRESET}' (PID {_carla_process.pid})", flush=True)
                except Exception as exc:
                    print(f"[pivocoder] Error al arrancar Carla: {exc}", flush=True)
                    proc = None
                else:
                    proc = _carla_process
            else:
                proc = _carla_process

        if proc is None:
            time.sleep(backoff)
            backoff = min(backoff * 2, _CARLA_BACKOFF_MAX)
            continue

        t_start = time.monotonic()
        try:
            rc = proc.wait()
        except Exception as exc:
            print(f"[pivocoder] Supervisor: error esperando Carla: {exc}", flush=True)
            rc = -1
        uptime = time.monotonic() - t_start

        with _carla_lock:
            if _carla_process is not proc:
                # _start_carla (cambio de preset) ya gestionó el relevo; no tocar nada.
                continue
            _carla_process = None

        print(f"[pivocoder] Carla terminó (rc={rc}, uptime={uptime:.1f}s). Reintento en {backoff}s.", flush=True)
        if uptime > 10:
            backoff = _CARLA_BACKOFF_INITIAL
        time.sleep(backoff)
        if uptime <= 10:
            backoff = min(backoff * 2, _CARLA_BACKOFF_MAX)


# Lanzar supervisor de Carla en segundo plano al importar el módulo
threading.Thread(target=_carla_supervisor, daemon=True, name="carla-supervisor").start()

# Iniciar cliente TCP para recibir eventos BPM
_bpm_state = start_tcp_client()


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/robot")
def robot():
    return render_template("robot.html", name="vocoder")


@app.route("/api/status")
def api_status():
    carla_pid = (
        _carla_process.pid
        if _carla_process is not None and _carla_process.poll() is None
        else None
    )
    bpm_snap = _bpm_state.snapshot()
    return jsonify({
        "jack": is_jack_running(),
        "carla": is_carla_running(),
        "preset": _current_preset,
        "carla_pid": carla_pid,
        "tcp_connected": bpm_snap["connected"],
        "bpm": bpm_snap["bpm"],
        "playing": bpm_snap["playing"],
    })


@app.route("/api/health")
def api_health():
    return jsonify({"ok": True})


@app.route("/robot_data")
def robot_data():
    usage = shutil.disk_usage("/")
    used_gb = usage.used / (1024 ** 3)
    total_gb = usage.total / (1024 ** 3)
    pct = usage.used / usage.total * 100
    bpm_snap = _bpm_state.snapshot()
    return jsonify({
        "disk_usage_percent": round(pct, 1),
        "disk_usage_string": f"{used_gb:.1f} GB / {total_gb:.1f} GB",
        "bpm": bpm_snap["bpm"],
        "tcp_connected": bpm_snap["connected"],
        "playing": bpm_snap["playing"],
        "last_sync_ms": bpm_snap["last_sync_ms"],
    })


@app.route("/api/client-errors")
def api_client_errors():
    active = is_carla_running()
    try:
        result = subprocess.run(
            ["journalctl", "--user", "-u", "carla", "--no-pager", "-n", "30", "--output=cat"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        lines = [
            ln for ln in result.stdout.splitlines()
            if any(k in ln.lower() for k in ("error", "warning", "critical", "fatal"))
        ]
        errors = "\n".join(lines[-20:])
    except Exception:
        errors = ""
    return jsonify({"is_active": active, "errors": errors})


@app.route("/restart-cliente", methods=["POST"])
def restart_cliente():
    with _carla_lock:
        try:
            _start_carla(FIXED_PRESET)
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500


@app.route("/api/restart", methods=["POST"])
def api_restart():
    with _carla_lock:
        try:
            _start_carla(FIXED_PRESET)
            return jsonify({"ok": True, "preset": _current_preset})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
