"""
Pestañas de la aplicación
"""

import tkinter as tk
from tkinter import ttk
import json
import os
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from PIL import Image, ImageTk

from ui_components import LogPanel
from midi_handler import MidiMessage
from config import (
    BATERIA_CONFIG_FILE, 
    IMAGES_DIR, 
    PAD_LIGHT_DURATION,
    VISUAL_IMAGE_SIZE
)


class BaseTab(ABC):
    """Clase base para todas las pestañas"""
    
    def __init__(self, parent: ttk.Notebook, name: str):
        self.name = name
        self.frame = ttk.Frame(parent, padding="10")
        
        self._setup_ui()
    
    @abstractmethod
    def _setup_ui(self):
        """Configurar la interfaz de la pestaña"""
        pass
    
    @abstractmethod
    def on_midi_message(self, msg) -> None:
        """Procesar un mensaje MIDI"""
        pass
    
    def log(self, message: str, tag: str = "info"):
        """Añadir mensaje al log (si tiene log_panel)"""
        if hasattr(self, 'log_panel') and self.log_panel:
            self.log_panel.log(message, tag)


class LogTab(BaseTab):
    """Pestaña de log de todos los eventos MIDI"""
    
    def __init__(self, parent: ttk.Notebook):
        super().__init__(parent, "Log")
    
    def _setup_ui(self):
        # Descripción
        desc_frame = ttk.Frame(self.frame)
        desc_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(
            desc_frame,
            text="Log de todos los eventos MIDI recibidos",
            font=("", 10, "italic")
        ).pack(anchor=tk.W)
        
        # Panel de log
        self.log_panel = LogPanel(self.frame, "Eventos MIDI")
        self.log_panel.pack(fill=tk.BOTH, expand=True)
    
    def on_midi_message(self, msg) -> None:
        """Procesar mensaje MIDI"""
        text, tag = MidiMessage.format_message(msg)
        self.log_panel.log(text, tag)
        self.log_panel.increment_count()


class DrumPad(tk.Canvas):
    """Widget de pad de batería que se ilumina"""
    
    def __init__(self, parent, name: str, label: str, color: str, size: int = 120):
        super().__init__(parent, width=size, height=size, highlightthickness=2, highlightbackground="#333")
        
        self.name = name
        self.label = label
        self.color = color
        self.off_color = "#2a2a2a"
        self.size = size
        self.is_lit = False
        self._after_id = None
        
        self._draw_pad(False)
    
    def _draw_pad(self, lit: bool):
        """Dibujar el pad"""
        self.delete("all")
        
        # Fondo
        fill = self.color if lit else self.off_color
        self.create_oval(10, 10, self.size - 10, self.size - 10, fill=fill, outline="#444", width=3)
        
        # Texto
        text_color = "white" if lit else "#666"
        self.create_text(
            self.size // 2, 
            self.size // 2, 
            text=self.label, 
            fill=text_color,
            font=("Arial", 14, "bold")
        )
    
    def light_on(self, duration: int = PAD_LIGHT_DURATION):
        """Encender el pad por un tiempo determinado"""
        # Cancelar timer anterior si existe
        if self._after_id:
            self.after_cancel(self._after_id)
        
        self.is_lit = True
        self._draw_pad(True)
        
        # Apagar después del tiempo
        self._after_id = self.after(duration, self.light_off)
    
    def light_off(self):
        """Apagar el pad"""
        self.is_lit = False
        self._draw_pad(False)
        self._after_id = None


class BateriaTab(BaseTab):
    """Pestaña para visualización de batería"""
    
    def __init__(self, parent: ttk.Notebook):
        self.config = self._load_config()
        self.pads: Dict[str, DrumPad] = {}
        super().__init__(parent, "Bateria")
    
    def _load_config(self) -> dict:
        """Cargar configuración de batería desde JSON"""
        try:
            with open(BATERIA_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error cargando configuración de batería: {e}")
            return {
                "channel": 0,
                "events": {},
                "labels": {"bombo": "Bombo", "caja1": "Caja 1", "caja2": "Caja 2", "crash": "Crash"},
                "colors": {"bombo": "#e74c3c", "caja1": "#3498db", "caja2": "#2ecc71", "crash": "#f39c12"}
            }
    
    def _setup_ui(self):
        # Descripción
        desc_frame = ttk.Frame(self.frame)
        desc_frame.pack(fill=tk.X, pady=(0, 20))
        ttk.Label(
            desc_frame,
            text="Visualización de eventos de batería",
            font=("", 10, "italic")
        ).pack(anchor=tk.W)
        
        # Info de configuración
        channel = self.config.get("channel", 0)
        ttk.Label(
            desc_frame,
            text=f"Canal MIDI: {channel + 1}",
            font=("", 9)
        ).pack(anchor=tk.W)
        
        # Frame central para los pads
        pads_frame = ttk.Frame(self.frame)
        pads_frame.pack(expand=True)
        
        # Crear pads
        labels = self.config.get("labels", {})
        colors = self.config.get("colors", {})
        
        # Fila superior: Crash
        top_frame = ttk.Frame(pads_frame)
        top_frame.pack(pady=10)
        
        if "crash" in labels:
            self.pads["crash"] = DrumPad(top_frame, "crash", labels["crash"], colors.get("crash", "#f39c12"))
            self.pads["crash"].pack()
        
        # Fila inferior: Caja2, Bombo, Caja1
        bottom_frame = ttk.Frame(pads_frame)
        bottom_frame.pack(pady=10)
        
        pad_order = ["caja2", "bombo", "caja1"]
        for pad_name in pad_order:
            if pad_name in labels:
                self.pads[pad_name] = DrumPad(
                    bottom_frame, 
                    pad_name, 
                    labels[pad_name], 
                    colors.get(pad_name, "#888")
                )
                self.pads[pad_name].pack(side=tk.LEFT, padx=15)
        
        # Último evento
        self.last_event_var = tk.StringVar(value="Esperando eventos...")
        ttk.Label(
            self.frame,
            textvariable=self.last_event_var,
            font=("Consolas", 10)
        ).pack(pady=(20, 0))
    
    def on_midi_message(self, msg) -> None:
        """Procesar mensaje MIDI para batería"""
        # Solo procesar note_on con velocidad > 0
        if msg.type != 'note_on' or msg.velocity == 0:
            return
        
        # Verificar canal
        expected_channel = self.config.get("channel", 0)
        if msg.channel != expected_channel:
            return
        
        # Buscar en eventos
        events = self.config.get("events", {})
        note_str = str(msg.note)
        
        if note_str in events:
            pads_to_light = events[note_str]
            
            # Iluminar pads correspondientes
            for pad_name in pads_to_light:
                if pad_name in self.pads:
                    self.pads[pad_name].light_on()
            
            # Actualizar último evento
            pad_names = ", ".join(pads_to_light)
            self.last_event_var.set(f"Nota {msg.note} → {pad_names}")


class VisualesTab(BaseTab):
    """Pestaña para visualización de imágenes por eventos CC"""
    
    def __init__(self, parent: ttk.Notebook):
        self.current_image = None
        self.photo_image = None
        self.canvas_size = (800, 600)
        super().__init__(parent, "Visuales")
    
    def _setup_ui(self):
        # Info del evento actual en la parte superior
        info_frame = ttk.Frame(self.frame)
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.cc_info_var = tk.StringVar(value="Esperando eventos CC...")
        ttk.Label(
            info_frame,
            textvariable=self.cc_info_var,
            font=("Consolas", 14, "bold")
        ).pack(side=tk.LEFT)
        
        self.path_info_var = tk.StringVar(value="")
        ttk.Label(
            info_frame,
            textvariable=self.path_info_var,
            font=("Consolas", 10),
            foreground="#888"
        ).pack(side=tk.RIGHT)
        
        # Frame para la imagen (ocupa todo el espacio)
        image_frame = ttk.Frame(self.frame)
        image_frame.pack(fill=tk.BOTH, expand=True)
        
        # Canvas para la imagen
        self.image_canvas = tk.Canvas(
            image_frame,
            bg="#0a0a0a",
            highlightthickness=0
        )
        self.image_canvas.pack(fill=tk.BOTH, expand=True)
        
        # Texto inicial
        self.image_canvas.create_text(
            400, 300,
            text="Sin imagen\n\nEnvía un evento CC MIDI",
            fill="#333",
            font=("Arial", 18),
            justify=tk.CENTER,
            tags="placeholder"
        )
        
        # Bind para redimensionar
        self.image_canvas.bind("<Configure>", self._on_resize)
    
    def on_midi_message(self, msg) -> None:
        """Procesar mensaje MIDI para visuales"""
        # Solo procesar control_change
        if msg.type != 'control_change':
            return
        
        # Solo canales 1-6 (índices 0-5)
        if msg.channel < 0 or msg.channel > 5:
            return
        
        # Ignorar CC 7 (volumen) - generado automáticamente
        if msg.control == 7:
            return
        
        # El CC número determina la carpeta principal
        # El valor determina la subcarpeta
        cc_num = msg.control
        cc_val = msg.value
        
        # Formatear como 3 dígitos
        folder_main = f"{cc_num:03d}"
        folder_sub = f"{cc_val:03d}"
        
        # Actualizar info
        self.cc_info_var.set(f"Canal: {msg.channel + 1} | CC: {cc_num} | Valor: {cc_val}")
        
        # Buscar imagen
        self._load_image(folder_main, folder_sub)
    
    def _on_resize(self, event):
        """Manejar redimensionado del canvas"""
        self.canvas_size = (event.width, event.height)
        # Redibujar imagen si existe
        if self.current_image:
            self._display_image(self.current_image)
    
    def _load_image(self, folder_main: str, folder_sub: str):
        """Cargar imagen desde la estructura de carpetas"""
        # Ruta base: ayuda_imagenes/XXX/YYY
        base_path = os.path.join(IMAGES_DIR, folder_main, folder_sub)
        
        image_path = None
        
        # Verificar si es una carpeta (animación) o un archivo
        if os.path.isdir(base_path):
            # Es una carpeta de animación, buscar el primer frame
            try:
                files = sorted([f for f in os.listdir(base_path) if f.endswith(('.png', '.jpg', '.jpeg', '.gif'))])
                if files:
                    image_path = os.path.join(base_path, files[0])
            except Exception:
                pass
        else:
            # Buscar archivo directamente
            for ext in ['.png', '.jpg', '.jpeg', '.gif']:
                test_path = base_path + ext
                if os.path.exists(test_path):
                    image_path = test_path
                    break
            
            # O buscar en la carpeta principal
            if not image_path:
                parent_path = os.path.join(IMAGES_DIR, folder_main)
                if os.path.isdir(parent_path):
                    for ext in ['.png', '.jpg', '.jpeg', '.gif']:
                        test_path = os.path.join(parent_path, folder_sub + ext)
                        if os.path.exists(test_path):
                            image_path = test_path
                            break
        
        if image_path and os.path.exists(image_path):
            self.current_image = image_path
            self._display_image(image_path)
            self.path_info_var.set(os.path.relpath(image_path, IMAGES_DIR))
        else:
            self.current_image = None
            self.path_info_var.set(f"No encontrado: {folder_main}/{folder_sub}")
            self._clear_image()
    
    def _display_image(self, path: str):
        """Mostrar imagen en el canvas"""
        try:
            # Cargar imagen con PIL
            img = Image.open(path)
            
            # Obtener tamaño del canvas
            canvas_w = max(self.canvas_size[0], 100)
            canvas_h = max(self.canvas_size[1], 100)
            
            # Redimensionar manteniendo aspecto
            img_ratio = img.width / img.height
            canvas_ratio = canvas_w / canvas_h
            
            if img_ratio > canvas_ratio:
                # Imagen más ancha
                new_w = canvas_w
                new_h = int(canvas_w / img_ratio)
            else:
                # Imagen más alta
                new_h = canvas_h
                new_w = int(canvas_h * img_ratio)
            
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            # Convertir a PhotoImage
            self.photo_image = ImageTk.PhotoImage(img)
            
            # Limpiar canvas
            self.image_canvas.delete("all")
            
            # Centrar imagen
            x = canvas_w // 2
            y = canvas_h // 2
            self.image_canvas.create_image(x, y, image=self.photo_image, anchor=tk.CENTER)
            
        except Exception as e:
            print(f"Error cargando imagen: {e}")
            self._clear_image()
    
    def _clear_image(self):
        """Limpiar el canvas"""
        self.image_canvas.delete("all")
        canvas_w = max(self.canvas_size[0], 100)
        canvas_h = max(self.canvas_size[1], 100)
        self.image_canvas.create_text(
            canvas_w // 2,
            canvas_h // 2,
            text="Sin imagen",
            fill="#333",
            font=("Arial", 18)
        )
