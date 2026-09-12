#!/usr/bin/env python3
"""Registro de la última reproducción en la carpeta de la canción.

El motor lo arranca en `Engine.start()` (Play en robotracker2 y en el
sinte) y lo reescribe al parar. En el hilo de audio solo se actualizan
contadores en memoria; el fichero se escribe desde un hilo daemon para
no bloquear el callback.

  <canción>/play_stats.txt

Desactivar: PLAY_STATS=0.
"""

from __future__ import annotations

import os
import platform
import socket
import sys
import threading
import time
from pathlib import Path

FILENAME = "play_stats.txt"
_ENV = "PLAY_STATS"
_SAMPLE_EVERY_S = 0.5
_SNAPSHOT_EVERY_S = 5.0
_BLOCK_RING = 400
_SYS_RING = 240          # ~2 minutos a 2 Hz


def enabled() -> bool:
    v = os.environ.get(_ENV, "1").strip().lower()
    return v not in ("0", "false", "off", "no")


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (p / 100.0)
    i = int(k)
    f = k - i
    if i + 1 >= len(s):
        return float(s[-1])
    return s[i] * (1.0 - f) + s[i + 1] * f


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text()
    except OSError:
        return None


def _self_cpu_s() -> float | None:
    raw = _read_text(Path("/proc/self/stat"))
    if raw is None:
        return None
    rparen = raw.rfind(")")
    if rparen < 0:
        return None
    fields = raw[rparen + 2:].split()
    try:
        utime = int(fields[11])
        stime = int(fields[12])
    except (IndexError, ValueError):
        return None
    try:
        clk = os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError):
        clk = 100
    return (utime + stime) / float(clk or 100)


def _sys_cpu_times() -> tuple[float, float] | None:
    """(busy, total) en jiffies, primera línea de /proc/stat."""
    raw = _read_text(Path("/proc/stat"))
    if raw is None:
        return None
    parts = raw.splitlines()[0].split()
    if not parts or parts[0] != "cpu":
        return None
    try:
        nums = [float(x) for x in parts[1:]]
    except ValueError:
        return None
    if len(nums) < 4:
        return None
    idle = nums[3] + (nums[4] if len(nums) > 4 else 0.0)
    total = sum(nums[:8]) if len(nums) >= 8 else sum(nums)
    return total - idle, total


def _mem_mb() -> tuple[float | None, float | None, float | None]:
    """(rss proceso, disponible, total) en MiB."""
    rss = None
    status = _read_text(Path("/proc/self/status"))
    if status:
        for line in status.splitlines():
            if line.startswith("VmRSS:"):
                try:
                    rss = int(line.split()[1]) / 1024.0
                except (IndexError, ValueError):
                    pass
                break
    avail = total = None
    info = _read_text(Path("/proc/meminfo"))
    if info:
        for line in info.splitlines():
            try:
                key, rest = line.split(":", 1)
                val = int(rest.split()[0]) / 1024.0
            except (ValueError, IndexError):
                continue
            if key == "MemAvailable":
                avail = val
            elif key == "MemTotal":
                total = val
    return rss, avail, total


def _loadavg() -> tuple[float, float, float] | None:
    try:
        return os.getloadavg()
    except (OSError, AttributeError):
        return None


def _thermals() -> list[tuple[str, float]]:
    root = Path("/sys/class/thermal")
    if not root.is_dir():
        return []
    out: list[tuple[str, float]] = []
    try:
        zones = sorted(root.glob("thermal_zone*"))
    except OSError:
        return []
    for z in zones:
        raw = _read_text(z / "temp")
        if raw is None:
            continue
        try:
            t = int(raw.strip()) / 1000.0
        except ValueError:
            continue
        typ = (_read_text(z / "type") or z.name).strip()
        out.append((typ, t))
    return out


def _cpu_mhz() -> float | None:
    raw = _read_text(Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"))
    if raw is None:
        return None
    try:
        return int(raw.strip()) / 1000.0
    except ValueError:
        return None


def _host_lines() -> list[str]:
    try:
        host = socket.gethostname()
    except OSError:
        host = platform.node() or "?"
    uname = f"{platform.system()} {platform.release()} {platform.machine()}"
    py = sys.version.split()[0]
    ncpu = os.cpu_count() or 0
    return [
        f"host        {host}",
        f"sistema     {uname}",
        f"python      {py}",
        f"cpus        {ncpu}",
    ]


class PlayLog:
    """Sesión de una reproducción. Un solo fichero, se sobrescribe."""

    def __init__(self, song_dir: Path | str | None, sample_rate: int):
        self.song_dir = Path(song_dir) if song_dir else None
        self.sr = int(sample_rate)
        self.source = ""
        self.blocksize_hint = 0
        self.enabled = enabled()
        self.active = False
        self._lock = threading.Lock()
        self._writer: threading.Thread | None = None
        self._gen = 0
        self._reset()

    def set_source(self, name: str):
        self.source = name or ""

    def set_blocksize(self, n: int):
        self.blocksize_hint = int(n) if n else 0

    def _reset(self):
        self.started_at = 0.0
        self.tempo = 0.0
        self.from_row: int | None = None
        self.reason = "en curso"
        self.blocks = 0
        self.block_ms: list[float] = []
        self.render_sum_ms = 0.0
        self.render_max_ms = 0.0
        self.budget_ms = 0.0
        self.over_budget = 0
        self.near_budget = 0
        self.xruns = 0
        self.last_xrun = ""
        self.dac_jumps = 0
        self.catch_ups = 0
        self.dac_jump_max_ms = 0.0
        self.voices_peak = 0
        self.peak_audio = 0.0
        self.cmds: list[str] = []
        self.cpu_proc: list[float] = []
        self.cpu_sys: list[float] = []
        self.rss_mb: list[float] = []
        self.avail_mb: list[float] = []
        self.total_mb: float | None = None
        self.temps: list[float] = []
        self.temp_names: list[str] = []
        self.loads: list[tuple[float, float, float]] = []
        self.mhz: list[float] = []
        self._last_sample = 0.0
        self._last_snapshot = 0.0
        self._prev_self_cpu: float | None = None
        self._prev_self_wall = 0.0
        self._prev_sys: tuple[float, float] | None = None
        self.host_lines = _host_lines() if self.enabled else []

    def begin(self, tempo: float = 0.0, from_row: int | None = None):
        if not self.enabled:
            return
        if self.active:
            self.finish("replaced")
        self._reset()
        self.active = True
        self.started_at = time.time()
        self.tempo = float(tempo)
        self.from_row = from_row
        self.reason = "en curso"
        self._sample_system(force=True)
        now = time.monotonic()
        self._last_sample = now
        self._last_snapshot = now
        self._schedule_write()

    def record_block(self, frames: int, elapsed_s: float,
                     voices: int = 0, peak: float = 0.0):
        if not self.enabled or not self.active:
            return
        ms = elapsed_s * 1000.0
        self.blocks += 1
        self.render_sum_ms += ms
        if ms > self.render_max_ms:
            self.render_max_ms = ms
        ring = self.block_ms
        if len(ring) < _BLOCK_RING:
            ring.append(ms)
        else:
            ring[self.blocks % _BLOCK_RING] = ms
        if frames > 0 and self.sr > 0:
            self.budget_ms = frames * 1000.0 / self.sr
            if self.blocksize_hint <= 0:
                self.blocksize_hint = frames
            if self.budget_ms > 0:
                if ms > self.budget_ms:
                    self.over_budget += 1
                elif ms > self.budget_ms * 0.75:
                    self.near_budget += 1
        if voices > self.voices_peak:
            self.voices_peak = voices
        if peak > self.peak_audio:
            self.peak_audio = peak
        now = time.monotonic()
        if now - self._last_sample >= _SAMPLE_EVERY_S:
            self._sample_system()
            self._last_sample = now
        if now - self._last_snapshot >= _SNAPSHOT_EVERY_S:
            self._last_snapshot = now
            self._schedule_write()

    def note_xrun(self, detail: str = ""):
        if not self.enabled or not self.active:
            return
        self.xruns += 1
        if detail:
            self.last_xrun = detail[:200]

    def note_dac_jump(self, ms: float, recovered: bool = False):
        if not self.enabled or not self.active:
            return
        self.dac_jumps += 1
        if ms > self.dac_jump_max_ms:
            self.dac_jump_max_ms = ms
        if recovered:
            self.catch_ups += 1

    def note_cmds(self, cmds):
        if cmds:
            self.cmds = sorted(str(c) for c in cmds)

    def snapshot(self, reason: str = "pause"):
        """Reescribe el fichero sin cerrar la sesión (pausa)."""
        if not self.enabled or not self.active:
            return
        self.reason = reason
        self._schedule_write()

    def finish(self, reason: str = "stop"):
        if not self.enabled or not self.active:
            return
        self.reason = reason
        self.active = False
        self._sample_system(force=True)
        self._schedule_write()

    def flush(self, timeout: float = 2.0):
        """Espera a que termine la escritura (tests)."""
        t = self._writer
        if t is not None and t.is_alive():
            t.join(timeout)

    def path(self) -> Path | None:
        if self.song_dir is None:
            return None
        return self.song_dir / FILENAME

    def _sample_system(self, force: bool = False):
        now = time.monotonic()
        if not force and now - self._last_sample < _SAMPLE_EVERY_S:
            return
        self._last_sample = now
        wall = time.monotonic()
        self_cpu = _self_cpu_s()
        if (self_cpu is not None and self._prev_self_cpu is not None
                and wall > self._prev_self_wall):
            dt = wall - self._prev_self_wall
            if dt > 0:
                pct = (self_cpu - self._prev_self_cpu) / dt * 100.0
                if 0.0 <= pct < 1000.0:
                    self._push(self.cpu_proc, max(0.0, pct))
        if self_cpu is not None:
            self._prev_self_cpu = self_cpu
            self._prev_self_wall = wall
        sys_t = _sys_cpu_times()
        if sys_t is not None and self._prev_sys is not None:
            db = sys_t[0] - self._prev_sys[0]
            dt = sys_t[1] - self._prev_sys[1]
            if dt > 0:
                self._push(self.cpu_sys, max(0.0, min(100.0, db / dt * 100.0)))
        if sys_t is not None:
            self._prev_sys = sys_t
        rss, avail, total = _mem_mb()
        if rss is not None:
            self._push(self.rss_mb, rss)
        if avail is not None:
            self._push(self.avail_mb, avail)
        if total is not None:
            self.total_mb = total
        load = _loadavg()
        if load is not None:
            self._push(self.loads, load)
        therms = _thermals()
        if therms:
            self.temp_names = [n for n, _ in therms]
            self._push(self.temps, max(t for _, t in therms))
        mhz = _cpu_mhz()
        if mhz is not None:
            self._push(self.mhz, mhz)

    @staticmethod
    def _push(ring: list, value):
        if len(ring) < _SYS_RING:
            ring.append(value)
        else:
            ring.pop(0)
            ring.append(value)

    def _schedule_write(self):
        # El texto se formatea aquí (copia de los contadores) para que un
        # begin() posterior no pise la sesión que se está escribiendo.
        dest = self.path()
        if dest is None or self.song_dir is None or not self.song_dir.is_dir():
            return
        self._gen += 1
        gen = self._gen
        text = self._format()

        def _run():
            if gen != self._gen:
                return
            try:
                tmp = dest.with_name(dest.name + ".tmp")
                tmp.write_text(text, encoding="utf-8")
                tmp.replace(dest)
            except OSError:
                try:
                    dest.with_name(dest.name + ".tmp").unlink()
                except OSError:
                    pass

        with self._lock:
            t = threading.Thread(target=_run, name="play-stats", daemon=True)
            self._writer = t
        t.start()

    def _format(self) -> str:
        elapsed = max(0.0, time.time() - self.started_at) if self.started_at else 0.0
        started = (time.strftime("%Y-%m-%d %H:%M:%S",
                                 time.localtime(self.started_at))
                   if self.started_at else "?")
        song = self.song_dir.name if self.song_dir else "?"
        song_path = str(self.song_dir) if self.song_dir else "?"
        bs = self.blocksize_hint
        budget = self.budget_ms
        if budget <= 0 and bs > 0 and self.sr > 0:
            budget = bs * 1000.0 / self.sr
        avg_ms = (self.render_sum_ms / self.blocks) if self.blocks else 0.0
        p50 = _pct(self.block_ms, 50)
        p95 = _pct(self.block_ms, 95)
        p99 = _pct(self.block_ms, 99)
        over_pct = (100.0 * self.over_budget / self.blocks) if self.blocks else 0.0
        lines = [
            f"# play_stats.txt — última reproducción (se sobrescribe)",
            f"fecha       {started}",
            f"origen      {self.source or 'engine'}",
            f"canción     {song}",
            f"ruta        {song_path}",
            *self.host_lines,
            f"tempo       {self.tempo:g}",
            f"sr          {self.sr}",
            f"blocksize   {bs or '?'}  (presupuesto {budget:.1f} ms)"
            if budget else f"blocksize   {bs or '?'}",
            f"desde fila  {self.from_row if self.from_row is not None else 'inicio'}",
            f"duración    {elapsed:.1f} s",
            f"fin         {self.reason}",
            "",
            "sistema",
            *_fmt_range("  CPU proceso", self.cpu_proc, "%"),
            *_fmt_range("  CPU sistema", self.cpu_sys, "%"),
            *_fmt_load(self.loads),
            *_fmt_range("  RAM rss   ", self.rss_mb, "MB"),
            *_fmt_range("  RAM libre ", self.avail_mb, "MB"),
        ]
        if self.total_mb is not None:
            lines.append(f"  RAM total     {self.total_mb:.0f} MB")
        lines.extend(_fmt_range("  temp     ", self.temps, "°C"))
        if self.temp_names:
            lines.append("  sensores      " + ", ".join(self.temp_names[:8]))
        lines.extend(_fmt_range("  cpu freq ", self.mhz, "MHz"))
        lines.extend([
            "",
            "audio",
            f"  bloques       {self.blocks}",
            f"  xruns         {self.xruns}"
            + (f"  ({self.last_xrun})" if self.last_xrun else ""),
            f"  saltos DAC    {self.dac_jumps}"
            + (f"  (máx {self.dac_jump_max_ms:.1f} ms)" if self.dac_jumps else ""),
            f"  catch-up      {self.catch_ups}",
            f"  render        med {avg_ms:.1f} ms  p50 {p50:.1f}  "
            f"p95 {p95:.1f}  p99 {p99:.1f}  máx {self.render_max_ms:.1f}",
            f"  sobrecarga    {self.over_budget} bloques ({over_pct:.1f}%) "
            f"por encima del presupuesto; {self.near_budget} apurados (>75%)",
            f"  voces máx     {self.voices_peak}",
            f"  pico audio    {self.peak_audio:.3f}",
            f"  comandos      {', '.join(self.cmds) if self.cmds else '(ninguno extra)'}",
            "",
            "diagnóstico",
        ])
        lines.extend(_diagnosis(self, budget, over_pct))
        lines.append("")
        return "\n".join(lines) + "\n"


def _fmt_range(label: str, values: list[float], unit: str) -> list[str]:
    if not values:
        return [f"{label}    (sin datos)"]
    return [
        f"{label}    med {_mean(values):.1f} {unit}  "
        f"máx {max(values):.1f} {unit}  último {values[-1]:.1f} {unit}"
    ]


def _fmt_load(loads: list[tuple[float, float, float]]) -> list[str]:
    if not loads:
        return ["  load 1/5/15   (sin datos)"]
    a, b, c = loads[-1]
    return [f"  load 1/5/15   {a:.2f}  {b:.2f}  {c:.2f}"]


def _diagnosis(log: PlayLog, budget: float, over_pct: float) -> list[str]:
    hints: list[str] = []
    if log.xruns:
        hints.append(
            "  xruns: el callback no llegó a tiempo (corte real de PortAudio). "
            "CPU, efectos LADSPA o blocksize pequeño."
        )
    if log.over_budget:
        hints.append(
            f"  sobrecarga: render() superó el presupuesto del bloque "
            f"({budget:.1f} ms) en {over_pct:.1f}% de los bloques."
        )
    elif log.near_budget and not log.xruns:
        hints.append(
            "  margen bajo: varios bloques por encima del 75% del presupuesto; "
            "aún no corta, pero falta holgura."
        )
    if log.dac_jumps and not log.xruns:
        hints.append(
            "  saltos del reloj del DAC: el driver/sistema movió el reloj; "
            "el audio de ese hueco se perdió."
        )
    if log.temps and max(log.temps) >= 80:
        hints.append(
            f"  temperatura alta ({max(log.temps):.0f} °C): posible thermal "
            "throttle (típico en handhelds)."
        )
    if log.avail_mb and min(log.avail_mb) < 150:
        hints.append(
            f"  poca RAM libre ({min(log.avail_mb):.0f} MB): el sistema puede "
            "empezar a paginar y cortar el audio."
        )
    if not hints:
        if log.blocks == 0:
            hints.append("  aún no ha sonado ningún bloque (o se cortó al arrancar).")
        else:
            hints.append("  sin xruns ni sobrecarga en esta pasada.")
    return hints
