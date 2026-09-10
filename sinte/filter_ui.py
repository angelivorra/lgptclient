"""Etiquetas amigables del filtro de instrumento (cut / res / type / mode).

Los valores internos siguen siendo 0-255 y los nombres del XML (original,
scream, lp, hp, bp, notch). Aquí solo se traduce para la UI: alguien que
no sepa de frecuencias tiene que entender qué mueve cada knob.
"""

FILTER_MODES = ("original", "scream", "lp", "hp", "bp", "notch")
SVF_MODES = ("lp", "hp", "bp", "notch")

MODE_SHORT = {
    "original": "LGPT",
    "scream": "scream",
    "lp": "grave",
    "hp": "agudo",
    "bp": "banda",
    "notch": "hueco",
}

MODE_LONG = {
    "original": "LGPT clásico",
    "scream": "scream (rasca)",
    "lp": "grave: deja graves",
    "hp": "agudo: quita graves",
    "bp": "banda: un trozo",
    "notch": "hueco: quita un trozo",
}

# Frases cortas para la celda de PHRASE/TABLE (~100 px).
_CUT_LP = ("muy sordo", "sordo", "medio", "claro", "muy claro", "abierto")
_CUT_HP = ("abierto", "casi todo", "quita poco", "quita graves",
           "muy fino", "solo agudos")
_CUT_SWEEP = ("en graves", "grave-medio", "en medios", "medio-agudo",
              "agudo", "en agudos")
_RES = ("limpio", "suave", "canta", "fuerte", "silba", "chilla")
_TYPE = ("grave", "casi grave", "mezcla", "casi agudo", "agudo", "agudo")


def clamp255(value) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(255, v))


def normalize_mode(mode) -> str:
    name = str(mode or "original")
    return name if name in FILTER_MODES else "original"


def mode_index(mode) -> int:
    return FILTER_MODES.index(normalize_mode(mode))


def mode_from_param(param: int) -> str:
    return FILTER_MODES[clamp255(param) % len(FILTER_MODES)]


def _band(value, labels) -> str:
    v = clamp255(value)
    if v >= 255:
        return labels[-1]
    for i, edge in enumerate((31, 79, 143, 207, 254)):
        if v <= edge:
            return labels[i]
    return labels[-1]


def cut_label(value, mode="original") -> str:
    """Cómo de abierto/cerrado está el corte, según el modo."""
    mode = normalize_mode(mode)
    if mode == "hp":
        return _band(value, _CUT_HP)
    if mode in ("bp", "notch"):
        return _band(value, _CUT_SWEEP)
    return _band(value, _CUT_LP)


def res_label(value) -> str:
    return _band(value, _RES)


def type_label(value) -> str:
    return _band(value, _TYPE)


def mode_label(mode, long=False) -> str:
    mode = normalize_mode(mode)
    return (MODE_LONG if long else MODE_SHORT)[mode]


def field_help(key: str, mode="original") -> str:
    """Ayuda del campo con foco en INSTRUMENT (una línea)."""
    mode = normalize_mode(mode)
    if key == "filter cut":
        if mode == "hp":
            return ("Corte: a la izquierda suena todo; a la derecha "
                    "solo queda lo agudo.")
        if mode in ("bp", "notch"):
            return ("Dónde actúa: izquierda = graves (boom), "
                    "derecha = agudos (brillo).")
        return ("Corte: izquierda = sonido sordo (solo graves), "
                "derecha = suena todo.")
    if key == "filter res":
        return ("Canto: izquierda = limpio, derecha = silba. "
                "Sube poco a poco.")
    if key == "filter type":
        if mode in SVF_MODES:
            return ("Mezcla grave/agudo: solo afecta a LGPT y scream. "
                    "En este modo no se usa.")
        return ("Mezcla del filtro LGPT: izquierda = grave, "
                "derecha = agudo.")
    if key == "filter mode":
        return ("Cómo filtra: LGPT/scream (viejos) o grave / agudo / "
                "banda / hueco (baratos).")
    return ""


PHRASE_FILTER_HELP = {
    "FCUT": "corte del filtro (sordo → abierto, o dónde actúa)",
    "FRES": "canto del filtro (limpio → silba)",
    "FMOD": "tipo: LGPT, scream, grave, agudo, banda, hueco",
}
