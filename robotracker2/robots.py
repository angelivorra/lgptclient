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
  cuando es "MDCC ccvv": control = (param>>8)&0x7F, value = param&0x7F. El
  cliente de la robota busca `images/{control:03d}/{value:03d}` (ver
  ansible/roles/cliente-actualiza, que despliega el `images/` del repo tal
  cual a /home/angel/images en las robotas). El "instrumento 80/81 por nota"
  de NOTAS.md es un mecanismo antiguo que el cliente actual ya no usa (solo
  lee MIDI CC, no nota, para imágenes): no se reutiliza aquí.

Carpetas de `images/` (una por "control" MDCC), según su contenido
(bin/genera.py clasifica igual): con fondo.png+textos = letra sincronizada
(no es un pick manual, la dispara el motor solo); con fondo.png+png/ =
imágenes estáticas (values = ficheros de png/); si no, subcarpetas numeradas
= animaciones (values = esas subcarpetas, cada una una secuencia de frames).
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

# Categoría de cada carpeta "control" de images/ (para etiquetar el SCREEN).
CC_LABELS = {1: "IMG", 2: "TXT", 3: "ANI"}
CC_LYRIC = 2                # control especial: letra sincronizada (no picker)


def hit_label(note):
    """Nombre del golpe para una nota (o el hex crudo si no está mapeada)."""
    return HIT_BY_NOTE.get(note, f"N{note:02X}")


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
