#!/usr/bin/env python3
"""Backend del mixer: el engine de sinte embebido en este proceso.

El mixer es standalone: no habla con ningún player por red, sino que crea
el `Player` de sinte/lgpt_player.py aquí dentro (mismo engine, mismo
robotraca.json), arranca la salida de audio y lo conduce desde la UI Kivy.
Sirve para probar y configurar cada canción: qué canal suena, cuál va al
vocoder, qué efectos lleva cada uno y qué knob maneja cada efecto, y
guardar el resultado en el robotraca.json de la canción.

Se reutiliza todo lo del player: la carga de canciones (`_load_song`, que
ya aplica el robotraca.json al arrancar el engine), los targets de los
knobs (`args.pots`/`args.pots_red`, los mismos que leen los pots físicos)
y la entrada MIDI del controlador, si está enchufado (los knobs físicos
funcionan igual que en la Pi).

Los cambios en vivo entran al engine por `Engine.push_event`, thread-safe
con el callback de audio. Lo que PERSISTE en el robotraca.json (mute,
vocoder, presence, fx, master, targets de knobs) se lleva además al
MODELO: un dict con la misma forma que el JSON, que `save()` vuelca a
disco conservando las claves que el mixer no edita. Lo que es solo en
vivo (vol/pan, giros de knob, pads) no toca el modelo.

Los métodos devuelven "OK" / "ERR,<msg>" (o dicts en las consultas) para
que la UI enseñe el resultado tal cual.
"""

from __future__ import annotations

import json
import sys
import threading
import tomllib
from pathlib import Path
from types import SimpleNamespace

SINTE_DIR = Path(__file__).resolve().parent.parent / "sinte"
if str(SINTE_DIR) not in sys.path:
    sys.path.insert(0, str(SINTE_DIR))

import sounddevice as sd  # noqa: E402

from lgpt_engine import EFFECT_PRESETS  # noqa: E402
from lgpt_player import Player, open_midi_input, parse_button_spec, \
    parse_pot_target as _parse_pot_target  # noqa: E402

# Claves del robotraca.json que edita el mixer, con su valor por defecto.
_MODEL_DEFAULTS = {
    "mute": [],
    "vocoder": [],
    "presence": [],
    "fx": {},
    "pots": {},
    "pots_red": [],
}


def parse_pot_target(spec: str):
    """"canales:param[:tope]" -> (canales, param, tope%), o None.

    Envoltura del parseo de lgpt_player con el tope en tanto por ciento,
    que es como lo maneja la UI de los knobs.
    """
    target = _parse_pot_target(spec)
    if target is None:
        return None
    canales, name, escala = target
    return canales, name, escala * 100.0


def _resolve_device(name: str | None):
    """El `output` del TOML ("IQaudIODAC") solo existe en la Pi; en el PC
    se cae al dispositivo por defecto."""
    if not name:
        return None
    try:
        for d in sd.query_devices():
            if name.lower() in d["name"].lower() \
                    and d["max_output_channels"] > 0:
                return d["name"]
    except Exception:
        pass
    return None


class MixerBackend:
    """Player + engine de sinte en proceso, con el modelo de config."""

    def __init__(self, delay: float = 0.0, midi: bool = True):
        """delay: el TOML trae 1 s para sincronizar con los clientes del
        robot; standalone estorba (un mute tardaría 1 s en oírse), así que
        por defecto se reproduce sin retardo."""
        cfg = tomllib.loads((SINTE_DIR / "lttileplayer.toml").read_text())
        audio_cfg = cfg.get("audio", {})
        midi_cfg = cfg.get("midi", {})

        songs = Path(cfg.get("songs_dir", "songs"))
        if not songs.is_absolute():
            songs = SINTE_DIR / songs
        wavs = audio_cfg.get("wavs_dir") or None
        if wavs is not None:
            wavs = Path(wavs)
            if not wavs.is_absolute():
                wavs = SINTE_DIR / wavs

        args = SimpleNamespace(
            songs=str(songs),
            device=_resolve_device(audio_cfg.get("output")),
            samplerate=audio_cfg.get("samplerate", 44100),
            blocksize=audio_cfg.get("blocksize", 2048),
            delay=delay,
            record=None,
            stream=None,
            midi=midi_cfg.get("input", "") if midi else "off",
            midi_out="",
            buttons={},
            hw_pots=cfg.get("pots", {}),
            pots=[],                       # targets (se arman por canción)
            pots_red=[],
            mute=cfg.get("channels", {}).get("mute", []),
            wavs_dir=str(wavs) if wavs else None,
            master_fx=cfg.get("master", {}),
            events={},
            pad_volume=audio_cfg.get("pad_volume", 60),
        )
        self.args = args
        try:
            self.player = Player(args)
        except SystemExit as exc:
            raise RuntimeError(str(exc)) from exc
        self.player.stream.start()
        self.midi_in = None
        if args.midi and args.midi != "off":
            try:
                self.midi_in = open_midi_input(
                    args.midi, self.player.engine_ref, self.player.ui_queue,
                    self.player.buttons, args.pots, args.pots_red)
            except Exception as exc:
                print(f"[mixer] sin entrada MIDI: {exc}")
        self._lock = threading.Lock()      # protege el modelo
        self._cfg: dict = {}
        self._cfg_song = -1
        # Carga la primera canción (empieza a sonar, como al darle a enter
        # en la UI curses) para que Play/Stop y los strips tengan engine.
        if self.player.projects:
            self.select(0)

    def close(self):
        engine = self._engine()
        if engine is not None:
            engine.panic()
        self.player.stream.stop()
        self.player.stream.close()
        if self.midi_in is not None:
            self.midi_in.close()

    # -- accesos internos ----------------------------------------------------

    def _engine(self):
        return self.player.engine_ref.get("engine")

    def _project_dir(self) -> Path:
        return self.player.projects[self.player.index]

    def _reload_model(self):
        """Carga el robotraca.json de la canción actual al modelo. Conserva
        las claves desconocidas para no perderlas al guardar."""
        cfg = {}
        try:
            cfg = json.loads(
                (self._project_dir() / "robotraca.json").read_text())
        except (OSError, json.JSONDecodeError):
            cfg = {}
        if not isinstance(cfg, dict):
            cfg = {}
        for key, default in _MODEL_DEFAULTS.items():
            value = cfg.get(key)
            if not isinstance(value, type(default)):
                cfg[key] = list(default) if isinstance(default, list) \
                    else dict(default)
        self._cfg = cfg
        self._cfg_song = self.player.index

    def _sync_model(self):
        """Si la canción cambió por otra vía (MIDI), recarga el modelo."""
        if self._cfg_song != self.player.index:
            self._reload_model()

    # -- consultas -------------------------------------------------------------

    def songs(self) -> dict:
        return {"songs": [p.name for p in self.player.projects],
                "current": self.player.index}

    def effects(self) -> list:
        """Efectos disponibles, en el orden de la cadena. Vivo: si el
        player gana presets nuevos (EFFECT_PRESETS), aparecen aquí solos."""
        return list(EFFECT_PRESETS)

    def get_config(self) -> dict:
        with self._lock:
            self._sync_model()
            return dict(self._cfg)

    def state(self) -> dict:
        engine = self._engine()
        state = {
            "song": self.player.index,
            "playing": False,
            "finished": False,
            "bpm": 0.0,
            "positions": [],
            "active": 0,
            "muted": [],
            "vocoder": [],
            "presence": [],
            "fx": {},
            "master": 100,
            "pads": 0,
        }
        if engine is not None:
            state.update({
                "playing": engine.playing,
                "finished": engine.finished,
                "bpm": round(engine.tempo, 1),
                "positions": engine.song_positions(),
                "active": engine.active_channels(),
                "muted": sorted(engine.muted),
                "vocoder": [ch.idx for ch in engine.channels
                            if ch.vocoder_out],
                "presence": [ch.idx for ch in engine.channels
                             if ch.fx_presence],
                "fx": {str(ch.idx): {k: round(v * 100) for k, v in
                                     ch.fx_amounts.items() if v > 0.001}
                       for ch in engine.channels},
                "master": round(100 * engine.master / engine.base_master)
                if engine.base_master else 100,
                "pads": len(engine.pad_samples),
            })
        return state

    # -- transporte y canciones ------------------------------------------------

    def select(self, index: int) -> str:
        if not 0 <= index < len(self.player.projects):
            return f"ERR,canción fuera de rango: {index}"
        self.player.index = index
        self.player._load_song(index)
        # _load_song arranca la reproducción (como el enter de la UI
        # curses); en el mixer la canción se carga PARADA y se le da al
        # play a mano. Aún no se ha disparado ninguna voz (eso pasa en
        # render), así que basta con bajar los flags.
        engine = self._engine()
        if engine is not None:
            engine.playing = False
            engine.finished = True
        with self._lock:
            self._reload_model()
        return "OK"

    def _transport(self, kind: str) -> str:
        engine = self._engine()
        if engine is None:
            return "ERR,no hay canción cargada"
        engine.push_event(kind)
        return "OK"

    def play(self) -> str:
        return self._transport("play")

    def pause(self) -> str:
        return self._transport("pause")

    def stop(self) -> str:
        return self._transport("stop")

    # -- canal: toggles que persisten -------------------------------------------

    def _channel_toggle(self, key: str, ch: int, on: bool) -> str:
        engine = self._engine()
        if engine is None:
            return "ERR,no hay canción cargada"
        if not 0 <= ch < len(engine.channels):
            return f"ERR,canal fuera de rango: {ch}"
        engine.push_event(key, ch, on)
        with self._lock:
            self._sync_model()
            channels = set(self._cfg[key])
            (channels.add if on else channels.discard)(ch)
            self._cfg[key] = sorted(channels)
        return "OK"

    def set_mute(self, ch: int, on: bool) -> str:
        return self._channel_toggle("mute", ch, on)

    def set_vocoder(self, ch: int, on: bool) -> str:
        return self._channel_toggle("vocoder", ch, on)

    def set_presence(self, ch: int, on: bool) -> str:
        return self._channel_toggle("presence", ch, on)

    # -- efectos y parámetros ----------------------------------------------------

    def set_fx(self, ch: int, preset: str, val127: int) -> str:
        """Cantidad de efecto de un canal: en vivo y persistida (campo fx)."""
        engine = self._engine()
        if engine is None:
            return "ERR,no hay canción cargada"
        if not 0 <= ch < len(engine.channels):
            return f"ERR,canal fuera de rango: {ch}"
        if preset not in EFFECT_PRESETS:
            return f"ERR,efecto desconocido: {preset}"
        val127 = max(0, min(127, val127))
        engine.push_event("param", ch, preset, val127)
        with self._lock:
            self._sync_model()
            fx = self._cfg["fx"].setdefault(str(ch), {})
            pct = round(val127 * 100 / 127)
            if pct > 0:
                fx[preset] = pct
            else:
                fx.pop(preset, None)
                if not fx:
                    self._cfg["fx"].pop(str(ch), None)
        return "OK"

    def param(self, ch: int, name: str, val127: int) -> str:
        """Parámetro genérico en vivo (lo usan los knobs), sin persistir."""
        engine = self._engine()
        if engine is None:
            return "ERR,no hay canción cargada"
        if not 0 <= ch < len(engine.channels):
            return f"ERR,canal fuera de rango: {ch}"
        engine.push_event("param", ch, name, max(0, min(127, val127)))
        return "OK"

    def set_vol(self, ch: int, val127: int) -> str:
        return self.param(ch, "volume", val127)

    def set_pan(self, ch: int, val127: int) -> str:
        return self.param(ch, "pan", val127)

    def set_master(self, pct: int) -> str:
        engine = self._engine()
        if engine is None:
            return "ERR,no hay canción cargada"
        pct = max(0, min(200, pct))
        # asignación de float: atómica, sin necesidad de pasar por la cola
        engine.master = engine.base_master * pct / 100.0
        with self._lock:
            self._sync_model()
            self._cfg["master"] = pct
        return "OK"

    # -- knobs ------------------------------------------------------------------

    def set_pot(self, n: int, spec_str: str) -> str:
        """Target del knob n (1-8): "off", "red" o "canales:param[:tope]".

        Reasigna en vivo (la lista args.pots se muta in-place para que el
        hilo MIDI, que guardó la referencia al abrir el puerto, vea el
        cambio) y actualiza el modelo.
        """
        if not 1 <= n <= 8:
            return f"ERR,knob fuera de rango: {n}"
        idx, key = n - 1, f"pot{n}"
        entry = self.args.hw_pots.get(key)
        hw_spec = parse_button_spec(entry.get("cc", "")) \
            if isinstance(entry, dict) else None
        spec_str = (spec_str or "").strip().lower() or "off"
        with self._lock:
            self._sync_model()
            pots_red = set(self._cfg["pots_red"])
            if spec_str == "off":
                self.args.pots[:] = [p for p in self.args.pots
                                     if p[2] != idx]
                self.args.pots_red[:] = [p for p in self.args.pots_red
                                         if p[1] != n]
                self._cfg["pots"].pop(key, None)
                pots_red.discard(key)
            elif spec_str == "red":
                if hw_spec is None:
                    return f"ERR,{key} no tiene CC físico en el TOML"
                self.args.pots[:] = [p for p in self.args.pots
                                     if p[2] != idx]
                self.args.pots_red[:] = [(s, c) for s, c in
                                         self.args.pots_red if c != n]
                self.args.pots_red.append((hw_spec, n))
                self._cfg["pots"].pop(key, None)
                pots_red.add(key)
            else:
                target = _parse_pot_target(spec_str)
                if target is None:
                    return f"ERR,target inválido: {spec_str}"
                if hw_spec is None:
                    return f"ERR,{key} no tiene CC físico en el TOML"
                self.args.pots[:] = [p for p in self.args.pots
                                     if p[2] != idx]
                self.args.pots.append((hw_spec, target, idx))
                self.args.pots_red[:] = [p for p in self.args.pots_red
                                         if p[1] != n]
                self._cfg["pots"][key] = spec_str
                pots_red.discard(key)
            self._cfg["pots_red"] = sorted(pots_red)
        return "OK"

    def netcc(self, control: int, val127: int) -> str:
        """Knob en modo red: reenvío de CC (canal virtual 9). Sin
        EventServer no sale a ninguna parte, pero el comportamiento es el
        mismo que en la Pi si el mixer corriera allí con eventos."""
        engine = self._engine()
        if engine is None:
            return "ERR,no hay canción cargada"
        engine.push_event("netcc", control, max(0, min(127, val127)))
        return "OK"

    # -- pads -------------------------------------------------------------------

    def pad(self, n: int) -> str:
        engine = self._engine()
        if engine is None:
            return "ERR,no hay canción cargada"
        if not 1 <= n <= 8:
            return f"ERR,pad fuera de rango: {n}"
        engine.push_event("trigger", n - 1)
        return "OK"

    # -- persistencia -------------------------------------------------------------

    def save(self) -> str:
        with self._lock:
            self._sync_model()
            cfg_file = self._project_dir() / "robotraca.json"
            try:
                cfg_file.write_text(json.dumps(self._cfg, indent=2,
                                               sort_keys=True) + "\n")
            except OSError as exc:
                return f"ERR,{exc}"
        print(f"[mixer] guardado {cfg_file}")
        return "OK"
