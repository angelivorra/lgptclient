"""Control MIDI del reproductor (botones + knobs), compartido con robotracker2.

Contiene la maquinaria de entrada MIDI que antes vivía en lgpt_player.py,
extraída aquí para que la usen también las apps que embeben el engine
(mixer/ ya la usaba vía lgpt_player; robotracker2 la importa vía su
sinte_bridge). Solo depende de lgpt_engine (y de mido, importado dentro de
`open_midi_input` para que el módulo se pueda importar sin mido instalado):

  - parse_button_spec / match_button: botones físicos (notas/CC) -> acción
  - parse_pot_target / match_pot: knobs -> (canales, parámetro, knob, escala)
  - match_pot_red: knobs que solo se reenvían por red
  - open_midi_input: abre el puerto y cablea botones a ui_queue, sampleN a
    los pads del engine y knobs/CC al engine (por referencia: las listas
    `pots`/`pots_red` se rellenan por canción y se evalúan en cada mensaje)
  - load_song_cfg / apply_song_config / build_song_pots: aplicación de
    robotraca.json de la canción (mute/vocoder/presence/fx/fx_mix/master/
    pad_volume) y construcción de los targets de knobs por canción.
"""

import json
import queue
from pathlib import Path

from lgpt_engine import EFFECT_PRESETS, NETCC_CHANNEL


def _pick_port(names: list[str], wanted: str | None, what: str) -> str | None:
    """Resuelve un puerto MIDI por nombre parcial. Si el nombre guardado
    incluye el id de cliente ALSA ("... 128:0"), también se prueba sin él
    (el número cambia entre arranques)."""
    if not names:
        print(f"[midi] no hay puertos MIDI de {what}; desactivado")
        return None
    if wanted:
        base = wanted.rsplit(" ", 1)[0]      # sin el "client:port" final
        for n in names:
            if wanted.lower() in n.lower() or base.lower() in n.lower():
                return n
        print(f"[midi] puerto '{wanted}' no encontrado; disponibles: {names}")
        return None
    return names[0]


def parse_button_spec(spec: str) -> tuple | None:
    """'note:canal:nota' o 'cc:canal:control' -> tupla normalizada, o None."""
    try:
        kind, ch, num = spec.split(":")
        ch, num = int(ch), int(num)
    except (ValueError, AttributeError):
        return None
    if kind == "note":
        return ("note_on", ch & 0x0F, num & 0x7F)
    if kind == "cc":
        return ("control_change", ch & 0x0F, num & 0x7F)
    return None


def match_button(mapping: dict, msg) -> str | None:
    """Devuelve la acción del botón que coincide con el mensaje, o None.

    mapping: acción -> spec de parse_button_spec()."""
    if msg.type == "note_on" and msg.velocity == 0:
        return None
    for action, spec in mapping.items():
        if spec is None:
            continue
        mtype, ch, num = spec
        if msg.type != mtype or getattr(msg, "channel", None) != ch:
            continue
        if mtype == "note_on" and msg.note == num:
            return action
        if mtype == "control_change" and msg.control == num and msg.value > 0:
            return action
    return None


def parse_pot_target(target: str) -> tuple | None:
    """'canales:parametro[:tope]' -> (canales, parametro, escala).

    canales: uno o varios separados por coma (`2` o `1,2`), canal tracker
    0-7; un mismo knob puede así mover varias pistas a la vez (p.ej. la
    reverb de todos los bajos).
    tope: recorrido máximo del knob en % (100 por defecto). Sirve para dejar
    un efecto en una zona discreta: `1,2:reverb:35` = de 0 a 35%.
    Devuelve None si no es válido.
    """
    try:
        parts = target.split(":")
    except AttributeError:
        return None
    if len(parts) == 2:
        chans_str, name = parts
        scale = 1.0
    elif len(parts) == 3:
        chans_str, name, top = parts
        try:
            scale = float(top) / 100.0
        except ValueError:
            return None
        if not 0.0 < scale <= 1.0:
            return None
    else:
        return None
    if not name:
        return None
    chans = []
    for c in chans_str.split(","):
        try:
            ci = int(c)
        except ValueError:
            return None
        if not 0 <= ci < 8:
            return None
        chans.append(ci)
    if not chans:
        return None
    return (tuple(chans), name, scale)


def match_pot(pots: list, msg) -> tuple | None:
    """Devuelve (canales, parámetro, nº de knob 0-7, escala) del pot que
    coincide con el mensaje, o None.

    pots: lista de (spec, target, idx) con target de parse_pot_target
    (canales|None, param, escala); canales None = se deriva del canal MIDI
    del mensaje (% 8). `idx` es el knob físico (pot1 -> 0), necesario para
    pintarlo en el visor."""
    if msg.type != "control_change":
        return None
    for spec, target, idx in pots:
        if spec is None:
            continue
        mtype, ch, num = spec
        if mtype == "control_change" and msg.channel == ch \
                and msg.control == num:
            chans, tparam, scale = target
            if chans is None:
                chans = (msg.channel % 8,)
            return chans, tparam, idx, scale
    return None


def match_pot_red(pots_red: list, msg) -> int | None:
    """Como `match_pot`, pero para pots configurados en `pots_red` (JSON de
    la canción): no controlan nada local, solo se reenvían por red. Devuelve
    el número de control con el que reenviar, o None."""
    if msg.type != "control_change":
        return None
    for spec, control in pots_red:
        mtype, ch, num = spec
        if mtype == "control_change" and msg.channel == ch \
                and msg.control == num:
            return control
    return None


def open_midi_input(port_name: str | None, engine_ref: dict,
                    ui_queue: queue.SimpleQueue, buttons: dict,
                    pots: dict, pots_red: list | None = None,
                    pots_red_global: list | None = None,
                    event_out=None):
    """Abre el puerto MIDI de entrada: botones a la UI y pots/CC al engine.

    engine_ref es un dict mutable con la clave "engine": el callback MIDI
    siempre usa el engine actual, aunque se cambie de canción. Puede traer
    además "on_trigger", hook opcional que se llama al disparar un pad
    sampleN (robotracker2 lo usa para asegurar el stream de audio: los
    pads suenan aunque la canción no esté reproduciéndose).
    Si hay pots configurados solo se procesan esos; si no, se usa el mapeo
    CC por defecto del engine (1/7/10/20).
    pots_red (opcional): pots que no controlan nada local, solo se reenvían
    por red (ver `pots_red` del JSON de la canción y `match_pot_red`).
    pots_red_global (opcional): pots de red FIJOS para todas las canciones
    (`red = true` en `[pots]` del TOML). Se reenvían por `event_out` directo,
    sin pasar por el engine, así funcionan también en la lista (sin canción)
    y en cualquier canción sin depender de su JSON. Ver el bloque en
    `on_message` antes del early-return de engine None.
    """
    if port_name == "off":
        return None
    try:
        import mido
    except ImportError:
        print("[midi] mido no disponible; control MIDI desactivado")
        return None

    chosen = _pick_port(mido.get_input_names(), port_name, "entrada")
    if chosen is None:
        return None

    def _handle(msg):
        # En modo calibración, TODO el MIDI se desvía a calib_queue (con
        # valor/velocidad) y no dispara botones/pots/engine. Ver _calib_view.
        if engine_ref.get("calib_mode"):
            cq = engine_ref.get("calib_queue")
            if cq is not None:
                num = getattr(msg, "note", getattr(msg, "control", 0))
                val = getattr(msg, "value", getattr(msg, "velocity", 0))
                cq.put((msg.type, getattr(msg, "channel", 0), num, val))
            return
        rq = engine_ref.get("raw_queue")
        if rq is not None:
            num = getattr(msg, "note", getattr(msg, "control", 0))
            rq.put((msg.type, getattr(msg, "channel", 0), num))
        if engine_ref.get("capture_mode"):
            return                          # CONFIG capturando: no disparar
        # Los botones mapeados tienen prioridad sobre pots y CC
        action = match_button(buttons, msg)
        if action is not None:
            if action.startswith("sample"):
                # pads sampler: disparan WAVs del banco (sample1 -> pad 1,
                # ver wavs_dir/pads.json). Pero en la lista (sin canción
                # cargada) no hay samples, así que cualquiera de esos pads
                # abre la calibración de motores.
                engine = engine_ref.get("engine")
                if engine is None:
                    ui_queue.put("calib")
                else:
                    try:
                        idx = int(action[6:]) - 1
                    except ValueError:
                        idx = 0
                    hook = engine_ref.get("on_trigger")
                    if hook is not None:
                        hook()      # p.ej. asegurar el stream de audio
                    engine.push_event("trigger", idx)
            else:
                ui_queue.put(action)
            return
        # Pots de red globales: fijos para todas las canciones y también en la
        # lista (sin canción cargada). Van ANTES del early-return de engine
        # None y se reenvían por `event_out` directo (que ya resuelve el
        # timestamp con o sin engine, ver EventMidiOut._ts): así estos knobs
        # modulan siempre la voz del vocoder, se esté donde se esté.
        if pots_red_global and event_out is not None:
            control = match_pot_red(pots_red_global, msg)
            if control is not None:
                event_out.cc(NETCC_CHANNEL, control, msg.value)
                return
        engine = engine_ref.get("engine")
        if engine is None:
            return
        # pots: la lista se rellena por canción; se evalúa EN CADA mensaje
        handled = False
        if pots:
            hit = match_pot(pots, msg)
            if hit is not None:
                chans, tparam, idx, scale = hit
                value = int(round(msg.value * scale))
                engine_ref.setdefault("pot_cc", {})[idx] = value
                for tch in chans:
                    engine.push_event("param", tch, tparam, value)
                handled = True
        if pots_red:
            control = match_pot_red(pots_red, msg)
            if control is not None:
                engine.push_event("netcc", control, msg.value)
                handled = True
        if not handled and not pots and msg.type == "control_change":
            engine.push_event("cc", msg.channel % 8, msg.control, msg.value)

    def on_message(msg):
        try:
            _handle(msg)
        except Exception as exc:              # noqa: BLE001 — un spec mal
            # configurado no debe matar el hilo del callback en silencio
            # (el usuario solo vería que el MIDI "no hace nada")
            print(f"[midi] error en callback: {exc!r}")

    port = mido.open_input(chosen, callback=on_message)
    print(f"[midi] entrada: '{chosen}'")
    return port


# -- robotraca.json (config por canción) ---------------------------------------

def load_song_cfg(project_dir: Path) -> dict:
    """Lee el robotraca.json de la canción, o {} si no hay o no es válido."""
    cfg_file = Path(project_dir) / "robotraca.json"
    if not cfg_file.is_file():
        return {}
    try:
        return json.loads(cfg_file.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[config] {cfg_file.name}: {exc}")
        return {}


def apply_song_config(engine, cfg: dict, pad_volume_default: float,
                      song_dir=None, pads_dir=None):
    """Aplica a `engine` la config de la canción (robotraca.json):
    mute de canales, presence, vocoder, cantidades y mezcla de efectos,
    master y volumen de pads. Sin JSON: todo a los valores por defecto.

    Los pads NO tienen configuración global, solo por canción: la clave
    "pads" del robotraca.json se resuelve contra la biblioteca de pads
    (`pads_dir`, p.ej. pads/ en la raíz del repo). Sin `pads_dir` (mixer,
    que sí tiene su banco global wavs_dir/pads.json), se recarga ese banco
    para que la mesa siga funcionando como hasta ahora."""
    engine.muted = set(cfg.get("mute", []))
    # Compensación de presencia al final de la cadena de FX (ver
    # Engine.render/Channel.fx_presence): opt-in por canal, solo para
    # la pista en la que se esté trabajando, no global.
    presence_channels = set(cfg.get("presence", []))
    for ch in engine.channels:
        ch.fx_presence = ch.idx in presence_channels
    # Pistas cuyo acorde (param1/param2, ver Engine._chord_tones) se
    # manda al vocoder por el evento ACRD además de/en vez de sonar
    # localmente (ver Channel.vocoder_out).
    vocoder_channels = set(cfg.get("vocoder", []))
    for ch in engine.channels:
        ch.vocoder_out = ch.idx in vocoder_channels
    # Cantidad de cada efecto por canal (0-100), persistida por el mixer:
    # {"fx": {"2": {"acid": 80, "delay": 40}}}. Son los mismos nombres de
    # EFFECT_PRESETS que usan los targets de los pots.
    fx_cfg = cfg.get("fx", {})
    if isinstance(fx_cfg, dict):
        for ch_str, amounts in fx_cfg.items():
            try:
                ci = int(ch_str)
            except (TypeError, ValueError):
                continue
            if not 0 <= ci < len(engine.channels) \
                    or not isinstance(amounts, dict):
                continue
            for name, val in amounts.items():
                if name in EFFECT_PRESETS:
                    try:
                        engine.channels[ci].fx_amounts[name] = \
                            float(val) / 100.0
                    except (TypeError, ValueError):
                        pass
    # Mezcla dry/wet de cada efecto por canal (0-100), persistida por el
    # mixer: {"fx_mix": {"2": {"acid": 50}}}. Ausencia = 100 (100% wet,
    # igual que sin esto).
    fx_mix_cfg = cfg.get("fx_mix", {})
    if isinstance(fx_mix_cfg, dict):
        for ch_str, amounts in fx_mix_cfg.items():
            try:
                ci = int(ch_str)
            except (TypeError, ValueError):
                continue
            if not 0 <= ci < len(engine.channels) \
                    or not isinstance(amounts, dict):
                continue
            for name, val in amounts.items():
                if name in EFFECT_PRESETS:
                    try:
                        engine.channels[ci].fx_mix[name] = \
                            float(val) / 100.0
                    except (TypeError, ValueError):
                        pass
    # Volumen general de la canción (0-200, 100 = el del proyecto LGPT).
    # Sirve para igualar la sonoridad entre canciones sin tocar el
    # lgptsav.dat: unas están mezcladas más fuerte que otras.
    master = cfg.get("master")
    if master is not None:
        try:
            engine.master = engine.base_master * float(master) / 100.0
        except (TypeError, ValueError):
            print(f"[config] master inválido: {master!r}")
    _apply_pad_volume(engine, cfg.get("pad_volume", pad_volume_default),
                      pad_volume_default)
    # Pads SIEMPRE POR CANCIÓN: {"pads": {"1": "nom.wav"}} resueltos contra
    # la biblioteca de pads (`pads_dir`). Sin la clave (o sin biblioteca:
    # la carpeta <song_dir>/pads de la canción), los pads quedan VACÍOS,
    # no se resucita ningún banco global. Solo sin pads_dir ni song_dir
    # (el mixer, que gestiona su propio banco wavs_dir/pads.json) se
    # recarga ese banco. getattr: el sinte de la Odin puede ser antiguo y
    # no traer load_pad_bank/reload_pad_samples.
    pads = cfg.get("pads")
    if pads_dir:
        if hasattr(engine, "load_pad_bank"):
            engine.load_pad_bank(pads if isinstance(pads, dict) else {},
                                 Path(pads_dir))
    elif isinstance(pads, dict) and song_dir:
        if hasattr(engine, "load_pad_bank"):
            engine.load_pad_bank(pads, Path(song_dir) / "pads")
    elif hasattr(engine, "reload_pad_samples"):
        engine.reload_pad_samples()


def _apply_pad_volume(engine, pv, pad_volume_default: float):
    """Campo pad_volume del robotraca.json (número = todos, o dict
    {"pad": pct}) al engine (0-1). Los pads que el dict no menciona
    siguen el volumen global (pad_volume_default), no el de fábrica."""
    if isinstance(pv, dict):
        engine.pad_volume_map = {
            int(k) - 1: float(v) / 100 for k, v in pv.items()}
        engine.pad_volume_default = float(pad_volume_default) / 100
    else:
        engine.pad_volume_map = {}
        engine.pad_volume_default = float(pv) / 100


def save_song_cfg(project_dir: Path, cfg: dict):
    """Persiste el robotraca.json de la canción (mismo formato que el
    mixer: indent=2, sort_keys, salto de línea final)."""
    cfg_file = Path(project_dir) / "robotraca.json"
    try:
        cfg_file.write_text(json.dumps(cfg, indent=2, sort_keys=True) + "\n")
    except OSError as exc:
        print(f"[config] no se pudo guardar {cfg_file.name}: {exc}")


def build_song_pots(hw_pots: dict, cfg: dict) -> tuple[list, list]:
    """Construye las listas (pots, pots_red) para open_midi_input.

    hw_pots: mapeo físico de knobs ({"pot3": {"cc": "cc:0:72"}, ...},
    como `[pots]` del TOML). `cfg`: robotraca.json de la canción.

    pots: (spec, target, idx) para los knobs con target en la canción
    (`"pots": {"pot3": "2:acid"}`).
    pots_red: (spec, control) para los knobs listados en `pots_red` del
    JSON: no controlan nada local, solo se reenvían por red (el control de
    red es el propio número de pot, "pot3" -> control 3).
    """
    pots = []
    for key, entry in hw_pots.items():
        if not isinstance(entry, dict):
            continue
        spec = parse_button_spec(entry.get("cc", ""))
        target = parse_pot_target(cfg.get("pots", {}).get(key, ""))
        if spec is None or target is None:
            continue
        try:
            idx = int(key[3:]) - 1     # "pot3" -> 2
        except ValueError:
            continue
        if not 0 <= idx < 8:
            continue
        pots.append((spec, target, idx))
    pots_red = []
    for key in set(cfg.get("pots_red", [])):
        entry = hw_pots.get(key)
        if not isinstance(entry, dict):
            continue
        spec = parse_button_spec(entry.get("cc", ""))
        if spec is None:
            continue
        try:
            control = int(key[3:])     # "pot3" -> 3
        except ValueError:
            continue
        pots_red.append((spec, control))
    return pots, pots_red
