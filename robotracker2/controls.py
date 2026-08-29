"""Controles parametrizables: entrada física -> botones lógicos estilo LGPT.

Los botones lógicos son fijos (dpad + A/B/L/R/START/SELECT/BACK, como en LGPT);
lo parametrizable es de qué tecla o botón de mando sale cada uno. En PC se usa
el teclado; en la Odin 2 Portal se usará el gamepad (perfil aparte, abajo).

La semántica (dpad = mover, A+dir = editar, L+dir = cambiar de pantalla, ...)
vive en la app/pantallas y trabaja SIEMPRE con botones lógicos, así que para
adaptar a otro hardware solo hay que tocar los mapas de este módulo.
"""

# --- Botones lógicos -----------------------------------------------------
UP = "up"
DOWN = "down"
LEFT = "left"
RIGHT = "right"
A = "a"
B = "b"
R2 = "r2"        # hombro derecho (PC: Ctrl derecho) — SELECCIÓN:
#                  R2+B = Ctrl+S (selección), R2+A = Ctrl+A (cortar/pegar)
L2 = "l2"        # hombro izquierdo (PC: Ctrl izquierdo) — NAVEGAR entre
#                  pantallas (L2+dpad) y mute (L2+S en SONG mientras suena)
START = "start"
SELECT = "select"
BACK = "back"

DPAD = frozenset({UP, DOWN, LEFT, RIGHT})

# =========================================================================
# Perfil PC (teclado) — lo que usas ahora
# =========================================================================
# keycode SDL -> botón lógico. Se mapea por keycode (no por codepoint) porque
# `on_key_up` de Kivy no trae codepoint; los keycodes de letras son ASCII.
# Ctrl derecho (306) e izquierdo (305) son botones DISTINTOS: R2 y L2.
KEYBOARD_KEYCODES = {
    273: UP, 274: DOWN, 276: LEFT, 275: RIGHT,   # flechas
    32: START,          # espacio = play/stop
    27: BACK,           # esc = volver
    9: SELECT,          # tab
    8: B, 127: B,       # backspace / supr = B (borrar)
    97: A,              # 'a' = A de LGPT
    115: B,             # 's' = B de LGPT
    306: R2,            # Ctrl derecho = R2 (navegar, cut/paste, selección)
    305: L2,            # Ctrl izquierdo = L2 (mute)
}


def key_to_button(keycode, codepoint=None):
    """Traduce un evento de teclado a un botón lógico (o None). Se resuelve por
    keycode para que valga igual en on_key_down y on_key_up."""
    return KEYBOARD_KEYCODES.get(keycode)


# =========================================================================
# Perfil gamepad (Odin 2 Portal)
# =========================================================================
# En la Odin (ROCKNIX) el mando se traduce a teclado con gptokeyb usando
# odin/robotracker2.gptk (X->a, B->s, R2->ctrl derecho, L2->ctrl izquierdo,
# dpad->flechas, Start->space, Back->esc), así que la app lee teclado y estos
# índices no se usan ahí. Este mapa es para lectura nativa del joystick (misma
# intención). Ajustar los índices al mando concreto si se usa sin gptokeyb.
GAMEPAD_BUTTONS = {
    2: A,        # X  -> A
    1: B,        # B  -> B
    5: R2,       # R  -> R2
    4: L2,       # L  -> L2
    7: START,    # Start -> play/stop
    6: BACK,     # Back  -> volver
}


def hat_to_buttons(hx, hy):
    """Valor del hat (dpad) del gamepad -> conjunto de botones lógicos."""
    buttons = set()
    if hy > 0:
        buttons.add(UP)
    elif hy < 0:
        buttons.add(DOWN)
    if hx < 0:
        buttons.add(LEFT)
    elif hx > 0:
        buttons.add(RIGHT)
    return buttons
