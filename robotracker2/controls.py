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
# La Odin (ROCKNIX) se lee por el JOYSTICK NATIVO (Kivy/SDL, sin mapeos):
# dpad = hat, X = A, B = B, Start/Back, y los gatillos analógicos L2/R2 por
# ejes (GAMEPAD_TRIGGER_AXES). gptokeyb (odin/robotracker2.gptk) quedó
# descartado: traducía los gatillos a Ctrl por teclado, pero depende de que
# SDL reconozca el mando como gamecontroller (la db de mapeos); si no lo
# reconoce (p.ej. el mando integrado de la Odin sin su entrada en la db), no
# llega nada. El joystick nativo no necesita mapeo, así que es la vía fiable.
# Índices de botón RAW del mando integrado de la Odin 2 (y del DualSense):
GAMEPAD_BUTTONS = {
    2: A,        # X  -> A
    1: B,        # B  -> B
    5: R2,       # R1 -> R2 (hombro digital: misma acción que el gatillo)
    4: L2,       # L1 -> L2 (hombro digital: misma acción que el gatillo)
    7: START,    # Start -> play/stop
    6: BACK,     # Back  -> volver
}

# Ejes analógicos RAW del joystick que actúan como gatillos L2/R2. En el
# mando integrado de la Odin 2 y en el DualSense, el eje 2 es el gatillo
# izquierdo (L2) y el 5 el derecho (R2); el valor va de 0 (sin pulsar) a
# 32767 (a fondo). Los ejes de los sticks (0/1/3/4) no se mapean.
GAMEPAD_TRIGGER_AXES = {2: L2, 5: R2}
# Umbral a partir del cual un gatillo cuenta como pulsado (~9% del recorrido,
# el mismo criterio que deadzone_triggers del .gptk).
TRIGGER_AXIS_THRESHOLD = 3000


def trigger_axis_buttons(axisid, value):
    """Botones de gatillo activos para un eje del joystick (o conjunto vacío).

    Para un eje de gatillo, devuelve {L2}/{R2} si el valor supera el umbral y
    el conjunto vacío si está por debajo (soltado). Para cualquier otro eje
    devuelve vacío siempre.
    """
    button = GAMEPAD_TRIGGER_AXES.get(axisid)
    if button is None:
        return frozenset()
    if value > TRIGGER_AXIS_THRESHOLD:
        return frozenset({button})
    return frozenset()


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
