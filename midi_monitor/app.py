"""
Aplicación principal MIDI Monitor
"""

import tkinter as tk
from tkinter import ttk
import platform

from config import (
    APP_NAME, 
    WINDOW_WIDTH, 
    WINDOW_HEIGHT, 
    WINDOW_MIN_WIDTH, 
    WINDOW_MIN_HEIGHT,
    QUEUE_UPDATE_INTERVAL
)
from midi_handler import MidiHandler
from ui_components import ConnectionPanel
from tabs import LogTab, BateriaTab, VisualesTab


class MidiMonitorApp:
    """Aplicación principal"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        
        # Manejador MIDI compartido
        self.midi = MidiHandler()
        
        # Pestañas
        self.tabs = []
        
        # Configurar estilo
        self._setup_style()
        
        # Configurar interfaz
        self._setup_ui()
        
        # Configurar cierre
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        
        # Iniciar procesamiento de cola
        self._process_queue()
    
    def _setup_style(self):
        """Configurar estilo de la aplicación"""
        style = ttk.Style()
        if platform.system() == "Windows":
            style.theme_use("vista")
        else:
            try:
                style.theme_use("clam")
            except:
                pass
    
    def _setup_ui(self):
        """Configurar la interfaz"""
        # Frame principal
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Info del sistema
        self._create_info_bar(main_frame)
        
        # Panel de conexión
        self.connection_panel = ConnectionPanel(
            main_frame,
            on_connect=self._on_connect,
            on_disconnect=self._on_disconnect,
            on_refresh=self._on_refresh_ports
        )
        self.connection_panel.pack(fill=tk.X, pady=(0, 10))
        
        # Notebook con pestañas
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Crear pestañas
        self._create_tabs()
        
        # Refrescar puertos
        self.root.after(100, self.connection_panel._on_refresh)
    
    def _create_info_bar(self, parent):
        """Crear barra de información"""
        info_frame = ttk.Frame(parent)
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Sistema
        system_info = f"Sistema: {platform.system()} {platform.release()}"
        ttk.Label(info_frame, text=system_info).pack(side=tk.LEFT)
        
        # Estado de mido
        if MidiHandler.is_available():
            backend = MidiHandler.get_backend_name()
            ttk.Label(
                info_frame, 
                text=f"✓ MIDI ({backend})",
                foreground="green"
            ).pack(side=tk.LEFT, padx=(20, 0))
        else:
            ttk.Label(
                info_frame,
                text="✗ MIDI no disponible",
                foreground="red"
            ).pack(side=tk.LEFT, padx=(20, 0))
    
    def _create_tabs(self):
        """Crear las pestañas de la aplicación"""
        # Pestaña Log
        log_tab = LogTab(self.notebook)
        self.notebook.add(log_tab.frame, text="Log")
        self.tabs.append(log_tab)
        self.midi.add_listener(log_tab.on_midi_message)
        
        # Pestaña Batería
        bateria = BateriaTab(self.notebook)
        self.notebook.add(bateria.frame, text="Batería")
        self.tabs.append(bateria)
        self.midi.add_listener(bateria.on_midi_message)
        
        # Pestaña Visuales
        visuales = VisualesTab(self.notebook)
        self.notebook.add(visuales.frame, text="Visuales")
        self.tabs.append(visuales)
        self.midi.add_listener(visuales.on_midi_message)
    
    def _on_connect(self, port_name: str):
        """Conectar al puerto MIDI"""
        try:
            self.midi.connect(port_name)
            self.connection_panel.set_connected(True, port_name)
            self._log_all(f"Conectado a '{port_name}'", "success")
        except Exception as e:
            self._log_all(f"Error al conectar: {e}", "error")
    
    def _on_disconnect(self):
        """Desconectar del puerto MIDI"""
        self.midi.disconnect()
        self.connection_panel.set_connected(False)
        self._log_all("Desconectado", "warning")
    
    def _on_refresh_ports(self):
        """Refrescar lista de puertos"""
        ports = MidiHandler.get_input_ports()
        return ports
    
    def _log_all(self, message: str, tag: str = "info"):
        """Enviar mensaje a todas las pestañas"""
        for tab in self.tabs:
            tab.log(message, tag)
    
    def _process_queue(self):
        """Procesar cola de mensajes MIDI"""
        self.midi.process_messages()
        self.root.after(QUEUE_UPDATE_INTERVAL, self._process_queue)
    
    def _on_closing(self):
        """Manejar cierre de la aplicación"""
        self.midi.disconnect()
        self.root.destroy()
    
    def run(self):
        """Ejecutar la aplicación"""
        self.root.mainloop()
