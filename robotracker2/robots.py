"""Constantes y helpers del canal de robotas (percusión + pantalla).

El canal 8 (índice 7) de la song usa siempre el instrumento MIDI 0x80 y
codifica dos cosas distintas en la misma phrase:

- **Golpe de percusión**: la nota del step. El mapeo nota->solenoide vive en
  los perfiles reales de las robotas (bin/cliente.maleta.json /
  cliente.sombrilla.json): 62=Bombo, 63=Caja1, 65=Caja2, 64=Bombo+Caja1,
  66=Bombo+Caja2, 67=Caja1+Caja2. NOTAS.md documenta otro rango (36-43) que ya
  no coincide con lo que usan las canciones reales ni los perfiles de las
  robotas: se ignora, HIT_NOTES es la fuente de verdad.

- **Evento de pantalla**: el comando FX1 (nunca FX2 en las canciones reales)
  cuando es "MDCC ccvv": control = (param>>8)&0x7F, value = param&0x7F.

El dispositivo NUNCA recibe `images/` en crudo: `ansible/roles/cliente-
actualiza` primero ejecuta `bin/genera.py <terminal>` en este PC (que LEE
`images/` y ESCRIBE los `.bin` ya renderizados en `img_output/<terminal>/`) y
luego sincroniza *eso* a `/home/angel/images` en la robota. Por carpeta
"control" (según cómo la clasifica bin/genera.py):

- **fondo.png + png/** → imágenes estáticas: cada `png/{value:03d}.png` es un
  icono pequeño que se compone CENTRADO sobre `fondo.png`.
- **fondo.png + fuente.ttf + textos** → letra sincronizada (control=2): cada
  LÍNEA de `images/002/textos` (compartido, no por canción — el `textos` de
  cada canción en `sinte/songs/*/textos` es un archivo aparte que solo usa el
  motor internamente) se renderiza como una palabra grande con efecto
  glow/glitch sobre `fondo.png`; `value` = índice de línea (0-based).
- si no, subcarpetas numeradas → animaciones: cada `{value:03d}/` es una
  secuencia de frames.

`bin/genera.py --markdown` (o con `markdown` en su config) además guarda una
miniatura YA renderizada de cada resultado en `ayuda_imagenes/{cc:03d}/...`
(mismo fondo+icono/glow/frame que ve el dispositivo real) — es exactamente lo
que queremos para previsualizar en el editor, así que `ayuda_preview_path` la
usa directamente en vez de recomponer nada a mano. Si no existe (no se ha
regenerado tras añadir algo nuevo), la previsualización queda vacía sin más.
"""

from pathlib import Path

ROBOT_TRACK = 7            # canal 8 (0-index)
ROBOT_INSTR = 0x80

# Golpe -> nota LGPT. Orden de ciclado (A+dir en la columna HIT).
HIT_NOTES = [
    ("BOMBO", 62),
    ("CAJA1", 63),
    ("CAJA2", 65),
    ("BOM+C1", 64),
    ("BOM+C2", 66),
    ("C1+C2", 67),
]
HIT_BY_NOTE = {note: label for label, note in HIT_NOTES}

# Piezas de cada golpe para iconos y pads LIVE: 62 bombo, 63 caja1, 65 caja2.
HIT_PARTS = {
    62: (62,),
    63: (63,),
    65: (65,),
    64: (62, 63),
    66: (62, 65),
    67: (63, 65),
}
HIT_PADS = (62, 63, 65)        # BOMBO / CAJA1 / CAJA2 (orden de la fila LIVE)
_EMPTY_NOTE = 0xFF

# Categoría de cada carpeta "control" de images/ (para etiquetar el SCREEN).
CC_LABELS = {1: "IMG", 2: "TXT", 3: "ANI"}
CC_LYRIC = 2                # control especial: letra sincronizada


def hit_label(note):
    """Nombre del golpe para una nota (o el hex crudo si no está mapeada)."""
    return HIT_BY_NOTE.get(note, f"N{note:02X}")


def hit_pad_notes(note):
    """Notas-pad (62/63/65) que enciende este golpe; vacío si no está mapeado."""
    return HIT_PARTS.get(note, ())


def mdcc_pack(cc, value):
    return ((cc & 0x7F) << 8) | (value & 0x7F)


def mdcc_unpack(param):
    return (param >> 8) & 0x7F, param & 0x7F


def screen_label(cc, value):
    tag = CC_LABELS.get(cc, f"CC{cc}")
    return f"{tag} {value:03d}"


def classify_folder(path):
    """Tipo de carpeta 'control' de images/: 'images' | 'anim' | 'lyric' | None."""
    path = Path(path)
    if (path / "textos").exists():
        return "lyric"
    if (path / "fondo.png").exists() and (path / "png").is_dir():
        return "images"
    if any(p.is_dir() for p in path.iterdir()) if path.is_dir() else False:
        return "anim"
    return None


def lyric_lines(images_dir):
    """Líneas de `images/002/textos` (compartido, igual criterio que
    bin/genera.py: recorta y descarta vacías). Cada índice es el `value` de
    un MDCC "TXT"."""
    if images_dir is None:
        return []
    path = Path(images_dir) / f"{CC_LYRIC:03d}" / "textos"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def ayuda_preview_path(ayuda_dir, cc, value):
    """Miniatura YA renderizada de (cc, value) (con el efecto/composición
    real), o None si no existe (falta generar `ayuda_imagenes/` con
    `bin/genera.py --markdown`, o (cc,value) no existe). Ficheros planos
    ({value:03d}.png) para imágenes/texto; carpeta de frames ({value:03d}/)
    para animaciones — se usa el primero."""
    if ayuda_dir is None:
        return None
    base = Path(ayuda_dir) / f"{cc:03d}"
    flat = base / f"{value:03d}.png"
    if flat.exists():
        return flat
    folder = base / f"{value:03d}"
    if folder.is_dir():
        frames = sorted(folder.glob("*.png"))
        if frames:
            return frames[0]
    return None


class RobotPlayback:
    """Estado LIVE del canal robot: último MDCC sostenido y golpe al avanzar.

    Se actualiza cada tick desde el engine (no desde el cursor del editor).
    `cc`/`value` se conservan entre steps y chains sin MDCC; `reset()` los
    borra (stop del transporte). `hit_note` solo vale el tick en que cambia
    `(phrase, phrase_pos)` y el step tiene nota.
    """

    def __init__(self):
        self._key = None
        self.cc = None
        self.value = None
        self.note = None
        self.hit_note = None
        self.playing = False
        self.muted = False

    def reset(self):
        self._key = None
        self.cc = None
        self.value = None
        self.note = None
        self.hit_note = None
        self.playing = False
        self.muted = False

    def update(self, engine):
        """Lee `engine.channels[ROBOT_TRACK]` y notes/cmd1/param1 del project."""
        if engine is None:
            self.reset()
            return self
        ch = engine.channels[ROBOT_TRACK]
        self.muted = ROBOT_TRACK in getattr(engine, "muted", ())
        chan_on = bool(ch.playing) and ch.phrase != _EMPTY_NOTE
        if not chan_on:
            self.playing = False
            self.note = None
            self.hit_note = None
            self._key = None
            return self
        self.playing = True
        key = (ch.phrase, ch.phrase_pos)
        advanced = key != self._key
        self._key = key
        proj = engine.project
        row = ch.phrase * 16 + ch.phrase_pos
        notes = proj.notes
        self.note = None
        self.hit_note = None
        if row >= len(notes):
            return self
        n = notes[row]
        if n != _EMPTY_NOTE:
            self.note = n
            if advanced:
                self.hit_note = n
        cmd1 = proj.cmd1
        if row < len(cmd1) and str(cmd1[row]).strip() == "MDCC":
            param = proj.param1[row] if row < len(proj.param1) else 0
            self.cc, self.value = mdcc_unpack(param)
        return self
