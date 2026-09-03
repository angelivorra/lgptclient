"""Control MIDI del reproductor (botones + knobs), como el mixer.

Envoltorio de sinte/midi_control.py (la misma maquinaria que usan
sinte/lgpt_player y mixer): abre la interfaz 'MIDI Control' del CONFIG y
cablea

  - botones físicos (`buttons` del config) -> ui_queue, drenada por la app
    en su hilo principal (play/stop/up/down); los sampleN los dispara el
    propio callback contra los pads del engine, sin pasar por la UI (con
    un hook opcional `on_trigger` justo antes: la app lo usa para asegurar
    el stream de audio, de modo que los pads suenan sin reproducir)
  - knobs (`hw_pots` del config) -> targets de robotraca.json de la canción
    cargada (push_event "param"); sin pots configurados en la canción, los
    CC sueltos caen al mapeo por defecto del engine (push_event "cc")

`open_midi_input` evalúa `engine_ref` y `pots` en CADA mensaje, así que
cambiar de canción no requiere reabrir el puerto: set_song muta esas listas
en sitio y además aplica la config de la canción al engine
(mute/vocoder/presence/fx/fx_mix/master/pad_volume/pads).

Los pads son SOLO por canción (clave "pads" del robotraca.json resuelta
contra la biblioteca de pads, pads/ en la raíz del repo): sin la clave, la
canción tiene los pads vacíos, no se resucita ningún banco global.

Los knobs (pantalla POTS) también son por canción: clave "pots" del
robotraca.json ("canal:efecto") + "fx_mix" para el porcentaje de mezcla.
Aquí solo se configuran los 4 del controlador (POTS_KNOBS = 1/2/5/6); la
lista de targets en vivo (self.pots, leída por el callback MIDI) se
reconstruye al momento con set_pot_canal/set_pot_efecto.
"""

import queue
from pathlib import Path

from sinte_bridge import EFFECT_PRESETS, _apply_pad_volume, \
    apply_song_config, build_song_pots, load_song_cfg, open_midi_input, \
    parse_button_spec, parse_pot_target, save_song_cfg

# Knobs configurables desde la pantalla POTS (los CC del LPD8: pot1/2/5/6).
POTS_KNOBS = [1, 2, 5, 6]


class MidiControl:
    def __init__(self, buttons, hw_pots, pad_volume, pads_dir=None,
                 on_trigger=None):
        # match_button espera specs YA parseados (tupla (tipo, canal, num)),
        # como los construye lgpt_player; los "note:canal:nota" del config
        # se parsean aquí. Los specs no válidos quedan en None y se ignoran.
        self.buttons = {action: parse_button_spec(spec)
                        for action, spec in (buttons or {}).items()}
        self.hw_pots = hw_pots
        self.pad_volume = pad_volume
        # Biblioteca de samples de los pads (clave "pads" del robotraca.json
        # de cada canción, resuelta contra esta carpeta).
        self._pads_dir = Path(pads_dir) if pads_dir else None
        self.ui_queue = queue.SimpleQueue()
        self.engine_ref = {"engine": None}
        if on_trigger is not None:
            # hook que el callback MIDI llama al disparar un pad (sampleN):
            # la app lo usa para crear el stream de audio si falta (los
            # pads suenan aunque la canción no esté reproduciéndose).
            self.engine_ref["on_trigger"] = on_trigger
        self.pots = []       # (spec, target, idx) de la canción cargada
        self._port = None
        self.error = None
        self._cfg = None          # robotraca.json de la canción cargada
        self._song_dir = None     # directorio de la canción cargada
        self._pot_sel = {}        # (canal, efecto) en edición sin target aún

    @property
    def active(self):
        return self._port is not None

    def open(self, port_name):
        """Abre la interfaz 'MIDI Control'. Sin interfaz configurada (None)
        no abre nada: el primer puerto del sistema no sirve, podría ser la
        interfaz de notas (a diferencia del TOML del player, que sí usa
        auto)."""
        self.close()
        if not port_name:
            return False
        self._port = open_midi_input(port_name, self.engine_ref,
                                     self.ui_queue, self.buttons, self.pots)
        return self._port is not None

    def close(self):
        if self._port is not None:
            try:
                self._port.close()
            except Exception:                # noqa: BLE001 — el puerto pudo
                pass                         # desconectarse con la app viva
            self._port = None

    def set_song(self, engine, song_dir):
        """Aplica el robotraca.json de `song_dir` al `engine` y reconfigura
        los knobs a sus targets de esa canción. El callback MIDI lee
        `engine_ref` y `pots` por referencia: no hay que reabrir el puerto.
        Conserva el cfg y el directorio para los cambios de la pantalla
        PADS (assign_pad/set_pad_volume, persistidos con save())."""
        self._song_dir = Path(song_dir)
        self._cfg = load_song_cfg(self._song_dir)
        self._pot_sel = {}            # borradores de POTS son por canción
        apply_song_config(engine, self._cfg, float(self.pad_volume),
                          song_dir=self._song_dir, pads_dir=self._pads_dir)
        pots, _pots_red = build_song_pots(self.hw_pots, self._cfg)
        self.pots.clear()
        self.pots.extend(pots)
        self.engine_ref["engine"] = engine

    def sync_mute(self):
        """Copia `engine.muted` al robotraca.json en memoria (clave
        "mute"). Se persiste con save(), como pads/knobs."""
        engine = self.engine_ref.get("engine")
        if self._cfg is None or engine is None:
            return
        self._cfg["mute"] = sorted(engine.muted)

    # -- pads sampler por canción (pantalla PADS) ------------------------
    def _save(self):
        if self._cfg is not None and self._song_dir is not None:
            save_song_cfg(self._song_dir, self._cfg)

    def assign_pad(self, pad, name):
        """Asigna (o quita, name=None) el WAV `name` (relativo a la
        biblioteca de pads, p.ej. "Distorted metal/Dip Spit.wav") al pad
        1-4: en memoria (self._cfg) y en vivo sobre el banco del engine
        para que los botones sampleN suenen ya. Se persiste en la clave
        "pads" del robotraca.json solo al guardar (save()), como el resto
        de la pantalla PADS. Con engine antiguo (sin load_pad_bank) solo
        queda en memoria; aplicará en la próxima carga."""
        if self._cfg is None or not 1 <= pad <= 4:
            return
        pads = self._cfg.get("pads")
        pads = dict(pads) if isinstance(pads, dict) else {}
        if name is None:
            pads.pop(str(pad), None)
        else:
            pads[str(pad)] = name
        self._cfg["pads"] = pads
        engine = self.engine_ref.get("engine")
        if engine is not None and hasattr(engine, "load_pad_bank"):
            engine.load_pad_bank(pads,
                                 self._pads_dir or self._song_dir / "pads")

    def set_pad_volume(self, pad, pct):
        """Volumen del pad 1-4 (0-100%): en vivo sobre el engine y en
        memoria ("pad_volume" del robotraca.json, siempre como dict; si
        era un número global se reparte a los 4 pads para que el resto
        conserve su volumen efectivo). Se persiste al guardar (save())."""
        if self._cfg is None or not 1 <= pad <= 4:
            return
        pct = max(0, min(100, int(pct)))
        pv = self._cfg.get("pad_volume")
        if isinstance(pv, dict):
            pv = dict(pv)
        elif isinstance(pv, (int, float)):
            pv = {str(i): int(pv) for i in range(1, 5)}
        else:
            pv = {}
        pv[str(pad)] = pct
        self._cfg["pad_volume"] = pv
        engine = self.engine_ref.get("engine")
        if engine is not None:
            _apply_pad_volume(engine, pv, float(self.pad_volume))

    def save(self):
        """Persiste en el robotraca.json de la canción la configuración en
        memoria (pads/pad_volume de PADS, pots/fx_mix de POTS y mute de
        SONG). Hasta que la app llama a esto (A sobre la fila GUARDAR de
        cada pantalla o Guardar de la canción) los cambios viven solo en
        self._cfg y en el engine."""
        self._save()

    def pads_state(self):
        """[(nombre_o_None, vol_pct)] de los pads 1-4 para la pantalla
        PADS (lee lo ya aplicado al engine, como MixerBackend._pad_volume_pct)."""
        engine = self.engine_ref.get("engine")
        out = []
        for i in range(4):
            if engine is not None:
                name = engine.pad_names[i] if i < len(engine.pad_names) \
                    else None
                vol = round(100 * engine.pad_volume_map.get(
                    i, engine.pad_volume_default))
            else:
                name, vol = None, round(self.pad_volume)
            out.append((name, vol))
        return out

    # -- knobs por canción (pantalla POTS) ------------------------------
    def _pot_state(self, pot):
        """(canal_1based_o_None, efecto_o_None, pct) del knob `pot`.

        El target lo manda el robotraca.json ("pots": {"pot1": "2:acid"});
        si aún no hay target válido, el borrador en edición (self._pot_sel)
        para poder elegir canal y efecto en cualquier orden."""
        cfg = self._cfg or {}
        spec = cfg.get("pots", {}).get(f"pot{pot}")
        target = parse_pot_target(spec) if spec else None
        canal = efecto = None
        if target is not None:
            canales, nombre, _escala = target
            canal = canales[0] + 1 if canales else None
            efecto = nombre if nombre in EFFECT_PRESETS else None
        else:
            canal, efecto = self._pot_sel.get(pot, (None, None))
        pct = 100
        if canal is not None and efecto is not None:
            fx_mix = cfg.get("fx_mix", {})
            pct = fx_mix.get(str(canal - 1), {}).get(efecto, 100)
        return canal, efecto, pct

    def pots_state(self):
        """[(canal, efecto, pct)] de los knobs 1/2/5/6 para la pantalla
        POTS (canal 1-8 o None; efecto de EFFECT_PRESETS o None; pct = el
        "fx_mix" de ese canal/efecto, 100 si no hay)."""
        return [self._pot_state(pot) for pot in POTS_KNOBS]

    def set_pot_canal(self, pot, delta):
        """Canal del knob `pot` +/- (cicla 1-8; None empieza en 1 u 8). En
        memoria ("pots" del robotraca.json como "canal-1:efecto"); si aún
        no hay efecto elegido, el canal queda en el borrador hasta elegirlo."""
        canal, efecto, _pct = self._pot_state(pot)
        if canal is None:
            canal = 1 if delta > 0 else 8
        else:
            canal = ((canal - 1 + delta) % 8) + 1
        self._set_pot(pot, canal, efecto)

    def set_pot_efecto(self, pot, delta):
        """Efecto del knob `pot` +/- (cicla "off" + EFFECT_PRESETS; "off"
        deja el knob sin target). En memoria, en vivo al instante."""
        canal, efecto, _pct = self._pot_state(pot)
        lista = ["off", *EFFECT_PRESETS]
        idx = lista.index(efecto) if efecto in lista else 0
        nuevo = lista[(idx + delta) % len(lista)]
        self._set_pot(pot, canal, nuevo if nuevo != "off" else None)

    def set_pot_efecto_nombre(self, pot, nombre):
        """Efecto del knob `pot` por nombre (la lista del picker de la
        pantalla EFECTOS); "off" deja el knob sin target. Como
        set_pot_efecto pero eligiendo directamente, sin ciclar."""
        canal, _efecto, _pct = self._pot_state(pot)
        self._set_pot(pot, canal, nombre if nombre != "off" else None)

    def _set_pot(self, pot, canal, efecto):
        """Actualiza la clave "pots" en memoria y reconstruye la lista de
        targets en vivo (self.pots se muta en sitio: el callback MIDI la
        lee en cada mensaje). El borrador conserva la elección a medias
        (canal sin efecto o al revés). Si el knob ya había mandado un CC,
        se reaplica al target nuevo y se pone a 0 el anterior: si no, al
        cambiar canal (p.ej. A+dir sobre CANAL, a una pista muteada) el
        giro se iba al canal nuevo y el bajo se quedaba sordo."""
        if self._cfg is None:
            return
        old_canal, old_efecto, _pct = self._pot_state(pot)
        pots = self._cfg.get("pots")
        pots = dict(pots) if isinstance(pots, dict) else {}
        if canal is not None and efecto is not None:
            pots[f"pot{pot}"] = f"{canal - 1}:{efecto}"
        else:
            pots.pop(f"pot{pot}", None)
        self._cfg["pots"] = pots
        self._pot_sel[pot] = (canal, efecto)
        self._rebuild_pots()
        self._reaplicar_pot(pot, old_canal, old_efecto, canal, efecto)

    def _reaplicar_pot(self, pot, old_canal, old_efecto, canal, efecto):
        """Mueve la cantidad del knob (último CC, o fx_amounts ya en el
        engine) del target viejo al nuevo."""
        engine = self.engine_ref.get("engine")
        if engine is None:
            return
        cc = (self.engine_ref.get("pot_cc") or {}).get(pot - 1)
        if cc is None and old_canal is not None and old_efecto is not None:
            try:
                amt = engine.channels[old_canal - 1].fx_amounts.get(
                    old_efecto, 0.0)
            except (AttributeError, IndexError):
                amt = 0.0
            if amt > 0.001:
                cc = int(round(amt * 127))
        moved = (old_canal, old_efecto) != (canal, efecto)
        if moved and old_canal is not None and old_efecto is not None:
            engine.push_event("param", old_canal - 1, old_efecto, 0)
        if canal is not None and efecto is not None and cc is not None:
            engine.push_event("param", canal - 1, efecto, cc)

    def set_pot_mix(self, pot, delta):
        """Porcentaje de mezcla dry/wet del efecto al que apunta el knob
        (0-100; la pantalla EFECTOS lo sube/baja fino ±1 o de 10 en 10):
        "fx_mix" del robotraca.json en memoria y en vivo por push_event
        ("fx_mix", canal, efecto, pct). 100 = sin entrada (el motor usa
        100% wet, comportamiento de hoy)."""
        canal, efecto, pct = self._pot_state(pot)
        if self._cfg is None or canal is None or efecto is None:
            return                        # sin target: el % no aplica a nada
        nuevo = max(0, min(100, pct + delta))
        fx_mix = self._cfg.get("fx_mix")
        fx_mix = dict(fx_mix) if isinstance(fx_mix, dict) else {}
        ch = str(canal - 1)
        fxm = dict(fx_mix.get(ch) or {})
        if nuevo >= 100:
            fxm.pop(efecto, None)
        else:
            fxm[efecto] = nuevo
        if fxm:
            fx_mix[ch] = fxm
        else:
            fx_mix.pop(ch, None)
        self._cfg["fx_mix"] = fx_mix
        engine = self.engine_ref.get("engine")
        if engine is not None:
            engine.push_event("fx_mix", canal - 1, efecto, nuevo)

    def _rebuild_pots(self):
        """Reconstruye self.pots (spec, target, idx) desde el robotraca.json
        en memoria, en sitio (la lista la compartió open_midi_input)."""
        pots, _pots_red = build_song_pots(self.hw_pots, self._cfg or {})
        self.pots.clear()
        self.pots.extend(pots)

    def clear_song(self):
        self.engine_ref["engine"] = None
        self.pots.clear()

    def drain(self):
        """Acciones de botón pendientes (llamar desde el hilo principal)."""
        acciones = []
        while True:
            try:
                acciones.append(self.ui_queue.get_nowait())
            except queue.Empty:
                return acciones
