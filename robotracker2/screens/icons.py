"""Glifos Phosphor (MIT, `fonts/Phosphor.ttf`) para la UI.

Un solo caché de texturas: tipos de pista, menú PROJECT y diálogos.
"""

from kivy.graphics import Color, Rectangle

from theme import TRACK_ICON_FONT

# Phosphor regular 2.1.2 (codepoints del webfont).
GLYPH = {
    "drum": "\uecac",            # vinyl-record
    "bass": "\ue44a",            # speaker-high
    "synth": "\ueaa0",           # wave-triangle
    "noise": "\ue802",           # waveform
    "robot": "\ue762",           # robot
    "vocoder": "\ue326",         # microphone
    "tempo": "\uec8e",           # metronome
    "master": "\ue44a",          # speaker-high
    "compact_seq": "\ue09a",     # arrows-in
    "compact_instr": "\uec54",   # broom
    "load": "\ue256",            # folder-open
    "save": "\ue248",            # floppy-disk
    "save_as": "\ue236",         # file-plus
    "exit": "\ue42a",            # sign-out
    "discard": "\ue4a6",         # trash
    "cancel": "\ue4f6",          # x
    "yes": "\ue184",             # check-circle
    "no": "\ue4f8",              # x-circle
    "pads": "\ue464",            # squares-four
    "sample": "\ue33c",          # music-note
    "volume": "\ue44a",          # speaker-high
    "empty": "\ue3d4",           # plus
    "effects": "\ue434",         # sliders-horizontal
    "eq": "\ue1c2",              # equalizer
    "fx": "\ue6b6",              # magic-wand
    "mix": "\ue3b6",             # percent
    "wet": "\ue210",             # drop
}

_cache = {}


def icon_texture(name, size):
    """Textura del glifo `name` a `size` px (blanco; se tiñe al pintar)."""
    key = (name, round(float(size), 1))
    tex = _cache.get(key)
    if tex is None:
        from kivy.core.text import Label as CoreLabel
        glyph = GLYPH.get(name, GLYPH["synth"])
        lbl = CoreLabel(text=glyph, font_size=max(8, int(size)),
                        font_name=TRACK_ICON_FONT, color=(1, 1, 1, 1))
        lbl.refresh()
        tex = lbl.texture
        _cache[key] = tex
    return tex


def draw_icon(cx, cy, size, name, color):
    """Pinta el icono `name` centrado en `(cx, cy)`."""
    tex = icon_texture(name, size)
    tw, th = tex.size
    Color(*color)
    Rectangle(texture=tex, pos=(cx - tw / 2, cy - th / 2), size=(tw, th))
