"""Pantalla LIVE: preview de lo que suena en el canal robot (solo lectura).

Muestra la imagen de SCREEN sostenida (último MDCC) y tres pads de batería
(BOMBO / CAJA1 / CAJA2) que destellan al golpear. A los lados de la
pantalla, las luces DMX de la pista LUCES (IZQ / DER) con su color,
brillo, fundido y estrobo en ese instante: el mismo estado que manda el
cable (`DmxOut.snapshot`). No edita la canción: la navegación es L+dpad;
START/STOP siguen siendo globales.
"""

import time
from pathlib import Path

from kivy.core.image import Image as CoreImage
from kivy.graphics import (Color, Ellipse, Line, Rectangle, RoundedRectangle,
                           ScissorPop, ScissorPush)
from kivy.metrics import dp
from kivy.uix.widget import Widget

from robots import (CC_LYRIC, HIT_PADS, anim_frame_paths, anim_fps,
                    ayuda_preview_path, classify_folder, hit_label,
                    hit_pad_notes, lyric_lines, screen_label)
from shared_visuals import HEIGHT as RIBBON_H
from shared_visuals import WIDTH as RIBBON_W
from shared_visuals import SPARK_CC, SPARK_VALUE, FadeBlack, FondoRibbon, SparkHit, VocoderNeon
from screens.hit_icons import draw_kick, draw_snare
from theme import (COLOR_BG, COLOR_BORDER, COLOR_EMPTY, COLOR_HEADER_TXT,
                   COLOR_HIT, COLOR_SCREEN, core_label)

def _punch_dark_alpha(img, lyric=False):
    """Si el PNG es opaco, el negro/casi-negro (y el azul-oscuro de la
    rejilla tron) pasa a alpha=0 — el mismo criterio que
    `DisplayExecutor._composite_rgb565` en el dispositivo.

    En letras el halo oscuro del glow taparía el fondo: se anula también
    la cola dim (rgb_sum < 70), igual que ``lyric_render``.
    """
    import numpy as np
    arr = np.array(img)
    r = arr[:, :, 0].astype(np.uint16)
    g = arr[:, :, 1].astype(np.uint16)
    b = arr[:, :, 2].astype(np.uint16)
    if lyric:
        transparent = (r + g + b) < 160
    else:
        if arr[:, :, 3].min() < 255:
            return img
        r5, g6, b5 = r >> 3, g >> 2, b >> 3
        lum = r5 + g6 + b5
        transparent = (lum <= 6) | ((b5 > r5) & (lum <= 25))
    arr[:, :, 3] = np.where(transparent, 0, 255)
    from PIL import Image as _PIL
    return _PIL.fromarray(arr, 'RGBA')


def _load_rgba_texture(path, punch_dark=False, punch_lyric=False):
    """Carga un PNG como textura RGBA preservando el canal alpha (via PIL)."""
    try:
        from PIL import Image as _PIL
        from kivy.graphics.texture import Texture as _Tex
        img = _PIL.open(str(path)).convert('RGBA')
        if punch_lyric or punch_dark:
            img = _punch_dark_alpha(img, lyric=punch_lyric)
        tex = _Tex.create(size=(img.width, img.height), colorfmt='rgba')
        tex.blit_buffer(img.tobytes(), colorfmt='rgba', bufferfmt='ubyte')
        tex.flip_vertical()
        return tex
    except Exception:
        pass
    try:
        return CoreImage(str(path)).texture
    except Exception:
        return None


PAD_H = dp(120)
GAP = dp(16)
FONT = dp(18)
FONT_SMALL = dp(14)
FONT_LYRIC = dp(36)
_PAD_DRAW = {62: lambda cx, cy, s, c: draw_kick(cx, cy, s, c),
             63: lambda cx, cy, s, c: draw_snare(cx, cy, s, c, hoop=False),
             65: lambda cx, cy, s, c: draw_snare(cx, cy, s, c, hoop=True)}
_PAD_NAME = {62: "BOMBO", 63: "CAJA1", 65: "CAJA2"}
_PAD_RIBBON = {62: "kick", 63: "snare1", 65: "snare2"}
LIGHT_W = dp(96)          # columna de cada foco a los lados de la pantalla


def light_visual(rgb, dim, strobe, now):
    """(r, g, b) 0-1 que se ve del foco: color × dimmer, y apagado en la
    fase oscura del estrobo (1-16 Hz aprox., como el PAR real)."""
    if strobe:
        hz = 1.0 + strobe / 255.0 * 15.0
        if (now * hz) % 1.0 >= 0.5:
            return (0.0, 0.0, 0.0)
    k = dim / 255.0 / 255.0
    return tuple(c * k for c in rgb)


class LiveGrid(Widget):
    def __init__(self, ayuda_dir=None, **kw):
        super().__init__(**kw)
        self.ayuda_dir = ayuda_dir
        self.cc = None
        self.value = None
        self.note = None
        self.playing = False
        self.muted = False
        self.pulse = {n: 0.0 for n in HIT_PADS}
        self._tex = {}
        self._img_cache = {}
        self._preview_path = None
        self._preview_tex = None
        self._loaded = (None, None)
        self._fondo_textures: list = []
        self._fondo_idx: int = 0
        self._fondo_elapsed: float = 0.0
        self._fondo_interval: float = 1.0
        self._images_dir: Path | None = None
        self._lyric_text: str | None = None  # texto activo CC=2
        self._anim_textures: list = []
        self._anim_idx: int = 0
        self._anim_elapsed: float = 0.0
        self._anim_interval: float = 1.0 / 30
        self.lights: list = []   # DmxOut.snapshot(): (nombre, rgb, dim, strobe, color)
        self.ribbon = FondoRibbon()
        self.neon = VocoderNeon()
        self.spark = SparkHit()
        self.fade = FadeBlack()
        self._spark_tex: dict = {}
        self._spark_on = False
        self._bpm = 180.0
        self._acrd_seq = None
        self.bind(pos=self._redraw, size=self._redraw)

    def set_lights(self, states):
        """Estado de las luces (DmxOut.snapshot). Redibuja si ha cambiado
        o si alguna está en estrobo (parpadea aunque el estado no cambie)."""
        states = list(states or [])
        if states != self.lights or any(s[3] for s in states):
            self.lights = states
            self._redraw()

    def reset(self):
        self.cc = None
        self.value = None
        self.note = None
        self.playing = False
        self.muted = False
        for n in HIT_PADS:
            self.pulse[n] = 0.0
        self._preview_path = None
        self._preview_tex = None
        self._lyric_text = None
        self._loaded = (None, None)
        self._fondo_textures = []
        self._fondo_idx = 0
        self._fondo_elapsed = 0.0
        self._images_dir = None
        self._clear_anim()
        self.ribbon = FondoRibbon()
        self.neon = VocoderNeon()
        self.spark.clear()
        self.fade.clear()
        self._acrd_seq = None
        self._redraw()

    def set_fondo(self, fondo_dir, images_dir=None, loop_s=1.0):
        """Carga las PNGs de fondos/{name}/ para el slideshow del live preview.
        loop_s: duración total del loop en segundos (interval = loop_s / n_imgs).
        images_dir: raíz de images/ para cargar imágenes MDCC sin procesar."""
        self._fondo_textures = []
        self._fondo_idx = 0
        self._fondo_elapsed = 0.0
        self._fondo_interval = 1.0  # se recalcula tras cargar imágenes
        self._images_dir = Path(images_dir) if images_dir else None
        self._img_cache.clear()
        # Limpia texturas líricas cacheadas (fuente puede cambiar por canción)
        self._tex = {k: v for k, v in self._tex.items()
                     if not (isinstance(k, tuple) and k[0] == "lyric")}
        self._loaded = (None, None)   # fuerza recarga de la imagen MDCC
        self._preview_path = None
        self._preview_tex = None
        self._clear_anim()
        if not fondo_dir:
            self._redraw()
            return
        p = Path(fondo_dir)
        if not p.is_dir():
            self._redraw()
            return
        for png in sorted(p.glob("*.png")):
            try:
                tex = CoreImage(str(png)).texture
                self._fondo_textures.append(tex)
            except Exception:
                pass
        n = len(self._fondo_textures)
        if n:
            self._fondo_interval = max(0.05, float(loop_s) / n)
        self._redraw()

    def set_bpm(self, bpm, base=None):
        """`base` es el tempo de la canción; `bpm` ya lleva el knob."""
        self._bpm = bpm if bpm and bpm > 0 else 180.0
        self.ribbon.set_bpm(bpm, base=base)

    def set_from(self, pb):
        """Copia RobotPlayback; destella pads si hay hit_note este tick."""
        started = pb.playing and not self.playing
        screen = (pb.cc, pb.value)
        changed = ((self.cc, self.value) != screen
                   or self.muted != pb.muted
                   or self.note != pb.note
                   or self.playing != pb.playing)
        if started:
            self.ribbon.reset_beat()
        self.cc, self.value = pb.cc, pb.value
        self.note = pb.note
        self.playing = pb.playing
        self.muted = pb.muted
        if screen != self._loaded:
            if self.playing and screen == (SPARK_CC, SPARK_VALUE):
                # La 01 no es el 404: chispazo, y fundido de 8 filas.
                self.spark.trigger()
                self.fade.start(self._bpm)
                self._loaded = screen
            else:
                self._load_preview()
            changed = True
        if pb.hit_note is not None:
            self.hit(pb.hit_note)
            changed = True
        if changed:
            self._redraw()

    def set_vocoder(self, seq, notes, vel):
        """Latigazo al avanzar la pista de voz. El primer seq solo engancha
        (no dispara el acorde que ya estaba sonando)."""
        if self._acrd_seq is None:
            self._acrd_seq = seq
            return
        if seq == self._acrd_seq:
            return
        self._acrd_seq = seq
        if notes:
            self.neon.pulse(notes, vel or 100)
            self._redraw()

    def _clear_anim(self):
        self._anim_textures = []
        self._anim_idx = 0
        self._anim_elapsed = 0.0
        self._anim_interval = 1.0 / 30

    def _load_anim(self, cc, value):
        """Carga los frames de una animación como RGBA (alpha real o punch)."""
        frames = anim_frame_paths(self._images_dir, cc, value)
        if not frames:
            return False
        key = f"anim:{self._images_dir}/{cc:03d}/{value:03d}"
        if key == self._preview_path and self._anim_textures:
            return True
        textures = []
        for png in frames:
            cache_key = f"rgba:{png}"
            if cache_key not in self._img_cache:
                self._img_cache[cache_key] = _load_rgba_texture(
                    png, punch_dark=True)
            tex = self._img_cache[cache_key]
            if tex is not None:
                textures.append(tex)
        if not textures:
            return False
        self._anim_textures = textures
        self._anim_idx = 0
        self._anim_elapsed = 0.0
        fps = anim_fps(self._images_dir, cc, value)
        self._anim_interval = 1.0 / fps
        self._preview_path = key
        self._preview_tex = None
        return True

    def _load_preview(self):
        self._loaded = (self.cc, self.value)
        self._lyric_text = None
        self._clear_anim()
        path = None
        if self.cc is not None and self.value is not None:
            # CC=2 (TXT): miniatura ya renderizada (glow real). Si no hay
            # thumb, cae a pintar la línea del banco (mismo criterio que
            # el navegador: se puede elegir igual).
            if self.cc == CC_LYRIC:
                tex = self._lyric_overlay_texture(self.value)
                if tex is not None:
                    self._preview_path = f"lyric-render:{self.value}"
                    self._preview_tex = tex
                    self._lyric_text = None
                    return
                if self._images_dir:
                    lines = lyric_lines(self._images_dir)
                    idx = max(0, self.value)
                    self._lyric_text = lines[idx] if idx < len(lines) else f"TXT {self.value:03d}"
                    self._preview_tex = None
                    self._preview_path = None
                    return
                path = ayuda_preview_path(self.ayuda_dir, self.cc, self.value)
                if path is not None:
                    key = f"lyric:{path}"
                    if key not in self._img_cache:
                        self._img_cache[key] = _load_rgba_texture(
                            path, punch_lyric=True)
                    self._preview_path = key
                    self._preview_tex = self._img_cache[key]
                    self._lyric_text = None
                    return
            if self._images_dir:
                kind = classify_folder(self._images_dir / f"{self.cc:03d}")
                if kind == "anim" and self._load_anim(self.cc, self.value):
                    return
                if self._fondo_textures:
                    # Fondo activo: PNG crudo con alpha, cargado como RGBA
                    raw = self._images_dir / f"{self.cc:03d}" / "png" / f"{self.value:03d}.png"
                    if raw.exists():
                        key = f"rgba:{raw}"
                        if key == self._preview_path:
                            return
                        if key not in self._img_cache:
                            self._img_cache[key] = _load_rgba_texture(raw)
                        self._preview_path = key
                        self._preview_tex = self._img_cache[key]
                        return
                    path = None
                else:
                    path = ayuda_preview_path(self.ayuda_dir, self.cc, self.value)
            else:
                path = ayuda_preview_path(self.ayuda_dir, self.cc, self.value)
        if path == self._preview_path:
            return
        self._preview_path = path
        self._preview_tex = None
        if path is None:
            return
        key = str(path)
        if key not in self._img_cache:
            tex = None
            if path.exists():
                try:
                    tex = CoreImage(key).texture
                except Exception:               # noqa: BLE001
                    tex = None
            self._img_cache[key] = tex
        self._preview_tex = self._img_cache[key]

    def _lyric_overlay_texture(self, value):
        """Letras con el mismo renderer de las robotas; el negro es alpha.

        No usa la miniatura de ayuda (a menudo trae el fondo baked y tapa
        el slideshow).
        """
        if not self._images_dir or value is None:
            return None
        key = f"lyric-render:{value}"
        if key in self._img_cache:
            return self._img_cache[key]
        tex = None
        try:
            from lyric_render import find_fuente, render_lyric_rgba
            from kivy.graphics.texture import Texture as _Tex
            font = find_fuente(self._images_dir / "002")
            lines = lyric_lines(self._images_dir)
            if font is not None and 0 <= value < len(lines):
                img = _punch_dark_alpha(
                    render_lyric_rgba(lines[value], font), lyric=True)
                tex = _Tex.create(size=img.size, colorfmt="rgba")
                tex.blit_buffer(img.tobytes(), colorfmt="rgba", bufferfmt="ubyte")
                tex.flip_vertical()
        except Exception:
            tex = None
        self._img_cache[key] = tex
        return tex

    def hit(self, note):
        for n in hit_pad_notes(note):
            self.pulse[n] = 1.0
            kind = _PAD_RIBBON.get(n)
            if kind:
                self.ribbon.pulse(kind)

    def tick_pulse(self, dt):
        decay = dt * 4.0
        alive = False
        for n in HIT_PADS:
            if self.pulse[n] > 0:
                self.pulse[n] = max(0.0, self.pulse[n] - decay)
                alive = True
        spark_on = self.spark.pending() > 0
        fade_on = self.fade.pending()
        if self.neon.level() > 0.03 or spark_on or fade_on:
            alive = True
            self._spark_on = spark_on
        elif self._spark_on:
            self._spark_on = False
            alive = True
        if self._fondo_textures:
            self.ribbon.step(time.time())
            self._fondo_elapsed += dt
            new_idx = int(self._fondo_elapsed / self._fondo_interval) % len(self._fondo_textures)
            if new_idx != self._fondo_idx:
                self._fondo_idx = new_idx
            alive = True
        if self._anim_textures:
            self._anim_elapsed += dt
            new_idx = int(self._anim_elapsed / self._anim_interval) % len(self._anim_textures)
            if new_idx != self._anim_idx:
                self._anim_idx = new_idx
                alive = True
        if alive:
            self._redraw()

    def _texture(self, text, font_size=FONT):
        key = (text, font_size)
        tex = self._tex.get(key)
        if tex is None:
            tex = core_label(text, font_size).texture
            self._tex[key] = tex
        return tex

    def _lyric_texture(self, text, font_size=FONT_LYRIC):
        """Textura de texto lírico usando images/002/fuente.ttf."""
        key = ("lyric", text, font_size)
        tex = self._tex.get(key)
        if tex is None:
            from kivy.core.text import Label as CoreLabel
            font_path = None
            if self._images_dir:
                for fname in ("fuente.ttf",):
                    p = self._images_dir / "002" / fname
                    if p.exists():
                        font_path = str(p)
                        break
            lbl = CoreLabel(text=text, font_size=font_size,
                            font_name=font_path or "Roboto")
            lbl.refresh()
            tex = lbl.texture
            self._tex[key] = tex
        return tex

    def _text_center(self, x, y, w, text, color, h, font_size=FONT):
        tex = self._texture(text, font_size)
        tw, th = tex.size
        Color(*color)
        Rectangle(texture=tex, size=(tw, th),
                  pos=(x + (w - tw) / 2, y + (h - th) / 2))

    def _redraw(self, *_):
        self.canvas.clear()
        with self.canvas:
            Color(*COLOR_BG)
            Rectangle(pos=self.pos, size=self.size)
            pad_y = self.y + GAP
            preview_bottom = pad_y + PAD_H + GAP
            avail_h = self.height - (preview_bottom - self.y) - GAP * 2 - dp(28)
            side = (LIGHT_W + GAP) if self.lights else 0
            avail_w = self.width - GAP * 2 - side * 2
            # Aspect ratio de la pantalla de las Pi: 800×480
            scale = min(avail_w / 800, avail_h / 480)
            pw = max(dp(1), 800 * scale)
            ph = max(dp(1), 480 * scale)
            px = self.x + (self.width - pw) / 2
            py = preview_bottom + GAP + dp(28)
            self._draw_preview(px, py, pw, ph)
            if self.lights:
                self._draw_lights(px, py, pw, ph)
            tag = "----"
            if self.cc is not None and self.value is not None:
                tag = screen_label(self.cc, self.value)
            ink = COLOR_SCREEN
            self._text_center(px, py - dp(28), pw, tag, ink,
                              h=dp(28), font_size=FONT)
            hit_txt = hit_label(self.note) if self.note is not None else "----"
            self._draw_pads(pad_y, hit_txt)

    def _draw_preview(self, px, py, pw, ph):
        Color(0.09, 0.10, 0.13, 1)
        Rectangle(pos=(px, py), size=(pw, ph))
        # Clip todo el contenido al área del preview para que el COVER no desborde
        ScissorPush(x=int(px), y=int(py), width=int(pw), height=int(ph))
        if self._fondo_textures:
            tex = self._fondo_textures[self._fondo_idx]
            tw, th = tex.size
            if tw and th:
                scale = max(pw / tw, ph / th)
                dw, dh = tw * scale, th * scale
                Color(1, 1, 1, 1)
                Rectangle(texture=tex, size=(dw, dh),
                          pos=(px + (pw - dw) / 2, py + (ph - dh) / 2))
            self._draw_ribbon(px, py, pw, ph)
        self._draw_neon(px, py, pw, ph)
        if self._lyric_text is not None:
            tex = self._lyric_texture(self._lyric_text, FONT_LYRIC)
            tw, th = tex.size
            # Escala para caber en el 80% del área (margen 10% por lado)
            scale = min(pw * 0.8 / tw, ph * 0.8 / th) if tw and th else 1
            dw, dh = tw * scale, th * scale
            Color(*COLOR_SCREEN)
            Rectangle(texture=tex, size=(dw, dh),
                      pos=(px + (pw - dw) / 2, py + (ph - dh) / 2))
        elif self.cc == CC_LYRIC and self._preview_tex is not None:
            Color(1, 1, 1, 1)
            Rectangle(texture=self._preview_tex, size=(pw, ph), pos=(px, py))
        elif self._anim_textures:
            tex = self._anim_textures[self._anim_idx]
            Color(1, 1, 1, 1)
            # Frames ya compuestos a 800×480: llenan el preview (el icono
            # queda al tamaño de diseño; el negro es alpha).
            Rectangle(texture=tex, size=(pw, ph), pos=(px, py))
        elif self._preview_tex is not None:
            tw, th = self._preview_tex.size
            # FIT con margen mínimo del 10% por lado (máx 80% del área)
            scale = min(pw * 0.8 / tw, ph * 0.8 / th) if tw and th else 1
            dw, dh = tw * scale, th * scale
            Color(1, 1, 1, 1)
            Rectangle(texture=self._preview_tex, size=(dw, dh),
                      pos=(px + (pw - dw) / 2, py + (ph - dh) / 2))
        self._draw_spark(px, py, pw, ph)
        a = self.fade.alpha()
        if a > 0.0:
            Color(0.0, 0.0, 0.0, a)
            Rectangle(pos=(px, py), size=(pw, ph))
        ScissorPop()
        Color(*COLOR_BORDER)
        Line(rectangle=(px, py, pw, ph), width=1.2)

    def _spark_texture(self, color, index):
        frames = self._spark_tex.get(color)
        if frames is None:
            from kivy.graphics.texture import Texture as _Tex
            frames = []
            for i in range(self.spark.frames):
                packed = self.spark.frame_rgba(i, color)
                if packed is None:
                    break
                raw, w, h = packed
                tex = _Tex.create(size=(w, h), colorfmt="rgba")
                tex.blit_buffer(raw, colorfmt="rgba", bufferfmt="ubyte")
                tex.flip_vertical()
                frames.append(tex)
            self._spark_tex[color] = frames
        if index < 0 or index >= len(frames):
            return None
        return frames[index]

    def _draw_spark(self, px, py, pw, ph):
        hits = self.spark.active_hits()
        if not hits:
            return
        sx = pw / RIBBON_W
        sy = ph / RIBBON_H
        for index, x, y, color in hits:
            tex = self._spark_texture(color, index)
            if tex is None:
                continue
            tw, th = tex.size
            Color(1, 1, 1, 1)
            Rectangle(
                texture=tex,
                size=(tw * sx, th * sy),
                pos=(px + x * sx, py + ph - (y + th) * sy),
            )

    def _draw_neon(self, px, py, pw, ph):
        """Mismos márgenes que el framebuffer: índice 0 = borde exterior."""
        cols = self.neon.columns()
        if cols is None:
            return
        sx = pw / RIBBON_W
        for i, (r, g, b, a) in enumerate(cols):
            a = float(a)
            if a < 0.02:
                break
            Color(float(r), float(g), float(b), a)
            w = sx + 0.6
            Rectangle(pos=(px + i * sx, py), size=(w, ph))
            Rectangle(pos=(px + pw - (i + 1) * sx, py), size=(w, ph))

    def _draw_ribbon(self, px, py, pw, ph):
        """Línea de reposo + figuras (mismo ribbon que las robotas)."""
        ys = self.ribbon.path_ys()
        sx = pw / RIBBON_W
        sy = ph / RIBBON_H
        figs = self.ribbon.snapshot_figures()

        def fb_to_kv(x, y):
            return px + x * sx, py + ph - float(y) * sy

        def in_gap(x):
            for fig in figs:
                half = fig["side"] / 2.0
                if half >= 0.5 and fig["x"] - half <= x <= fig["x"] + half:
                    return True
            return False

        def stroke(points):
            if len(points) < 4:
                return
            beat = self.ribbon.beat_pulse()
            Color(0.0, 0.90, 1.0, 0.16 + 0.22 * beat)
            Line(points=points, width=2.8 + 2.2 * beat, cap="round", joint="round")
            Color(0.0, 0.90, 1.0, 0.42 + 0.38 * beat)
            Line(points=points, width=1.6 + 1.4 * beat, cap="round", joint="round")
            Color(0.75, 1.0, 1.0, 0.80 + 0.20 * beat)
            Line(points=points, width=1.05 + 0.55 * beat, cap="round", joint="round")

        seg = []
        for x, y in enumerate(ys):
            if in_gap(x):
                stroke(seg)
                seg = []
                continue
            seg.extend(fb_to_kv(x, y))
        stroke(seg)

        for fig in figs:
            side = fig["side"]
            if side < 1.0:
                continue
            cx, cy = fig["x"], fig["y"]
            x0, y_top = fb_to_kv(cx - side / 2.0, cy - side / 2.0)
            x1, y_bot = fb_to_kv(cx + side / 2.0, cy + side / 2.0)
            rx, ry = min(x0, x1), min(y_top, y_bot)
            rw, rh = abs(x1 - x0), abs(y_bot - y_top)
            fr, fg, fb = [c / 255.0 for c in fig["fill"]]
            Color(fr, fg, fb, 1)
            if fig["shape"] == "circle":
                Ellipse(pos=(rx, ry), size=(rw, rh))
            else:
                Rectangle(pos=(rx, ry), size=(rw, rh))
            or_, og, ob = [c / 255.0 for c in fig["outline"]]
            Color(or_, og, ob, 1)
            if fig["shape"] == "circle":
                Line(ellipse=(rx, ry, rw, rh), width=1.4)
            else:
                Line(rectangle=(rx, ry, rw, rh), width=1.4)

    def _draw_lights(self, px, py, pw, ph):
        """Focos PAR a los lados de la pantalla: la 1ª a la izquierda, la 2ª
        a la derecha (más de dos: se reparten alternando)."""
        now = time.monotonic()
        lens = min(LIGHT_W * 0.78, ph * 0.42)
        for i, (name, rgb, dim, strobe, cname) in enumerate(self.lights):
            left = i % 2 == 0
            row = i // 2
            cx = (px - GAP - LIGHT_W / 2) if left else (px + pw + GAP + LIGHT_W / 2)
            cy = py + ph * 0.62 - row * (lens + dp(48))
            r, g, b = light_visual(rgb, dim, strobe, now)
            lit = max(r, g, b)
            # halo
            if lit > 0.02:
                for grow, alpha in ((1.9, 0.10), (1.45, 0.22)):
                    d = lens * grow
                    Color(r, g, b, alpha * lit)
                    Ellipse(pos=(cx - d / 2, cy - d / 2), size=(d, d))
            # carcasa
            body = lens + dp(12)
            Color(0.13, 0.14, 0.17, 1)
            RoundedRectangle(pos=(cx - body / 2, cy - body / 2),
                             size=(body, body), radius=[dp(12)])
            Color(*COLOR_BORDER)
            Line(rounded_rectangle=(cx - body / 2, cy - body / 2, body, body,
                                    dp(12)), width=1.2)
            # lente: color de la luz sobre fondo oscuro
            Color(0.05, 0.05, 0.06, 1)
            Ellipse(pos=(cx - lens / 2, cy - lens / 2), size=(lens, lens))
            if lit > 0.0:
                Color(r, g, b, 1)
                Ellipse(pos=(cx - lens / 2, cy - lens / 2), size=(lens, lens))
            label = f"{name} STRB" if strobe else name
            self._text_center(cx - LIGHT_W / 2, cy - body / 2 - dp(26),
                              LIGHT_W, label, COLOR_HEADER_TXT,
                              h=dp(22), font_size=FONT_SMALL)
            # nombre del color (se lee aunque no se distingan los colores)
            if cname and cname != "APAGA" and dim:
                self._text_center(cx - LIGHT_W / 2, cy - body / 2 - dp(48),
                                  LIGHT_W, cname, (1, 1, 1, 1),
                                  h=dp(22), font_size=FONT_SMALL)

    def _draw_pads(self, y, hit_txt):
        w = min(self.width - GAP * 2, dp(720))
        x0 = self.x + (self.width - w) / 2
        cell = (w - GAP * 2) / 3
        for i, note in enumerate(HIT_PADS):
            x = x0 + i * (cell + GAP)
            a = self.pulse[note]
            r, g, b, _a = COLOR_HIT
            Color(r, g, b, a * 0.35 + 0.08)
            RoundedRectangle(pos=(x, y), size=(cell, PAD_H), radius=[dp(10)])
            Color(*COLOR_BORDER)
            Line(rectangle=(x, y, cell, PAD_H), width=1.2)
            ink = tuple(min(1, c + (1 - c) * a) for c in COLOR_HIT[:3]) + (1,)
            draw = _PAD_DRAW[note]
            draw(x + cell / 2, y + PAD_H * 0.58, min(cell, PAD_H) * 0.42, ink)
            self._text_center(x, y + dp(8), cell, _PAD_NAME[note],
                              ink if a > 0.05 else COLOR_HEADER_TXT,
                              h=dp(24), font_size=FONT_SMALL)
        self._text_center(x0, y + PAD_H + dp(2), w, hit_txt,
                          COLOR_HIT if self.note is not None else COLOR_EMPTY,
                          h=dp(22), font_size=FONT_SMALL)
