"""
Componentes de interfaz de usuario reutilizables
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
from datetime import datetime

from config import LOG_COLORS, LOG_BG_COLOR, LOG_FG_COLOR, LOG_FONT


class LogPanel(ttk.Frame):
    """Panel de log con scroll y colores"""
    
    def __init__(self, parent, title: str = "Log"):
        super().__init__(parent)
        
        self.event_count = 0
        self.autoscroll = True
        
        self._setup_ui(title)
    
    def _setup_ui(self, title: str):
        # Frame del log
        log_frame = ttk.LabelFrame(self, text=title, padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        # Área de texto con scroll
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            font=LOG_FONT,
            bg=LOG_BG_COLOR,
            fg=LOG_FG_COLOR,
            insertbackground="white"
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.config(state=tk.DISABLED)
        
        # Configurar tags de colores
        for tag, color in LOG_COLORS.items():
            self.log_text.tag_configure(tag, foreground=color)
        
        # Frame inferior
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill=tk.X, pady=(5, 0))
        
        # Contador de eventos
        self.event_count_var = tk.StringVar(value="Eventos: 0")
        ttk.Label(bottom_frame, textvariable=self.event_count_var).pack(side=tk.LEFT)
        
        # Autoscroll checkbox
        self.autoscroll_var = tk.BooleanVar(value=True)
        self.autoscroll_var.trace_add('write', self._on_autoscroll_change)
        ttk.Checkbutton(
            bottom_frame,
            text="Auto-scroll",
            variable=self.autoscroll_var
        ).pack(side=tk.RIGHT)
        
        # Botón limpiar
        ttk.Button(
            bottom_frame,
            text="Limpiar",
            command=self.clear
        ).pack(side=tk.RIGHT, padx=(0, 10))
    
    def _on_autoscroll_change(self, *args):
        self.autoscroll = self.autoscroll_var.get()
    
    def log(self, message: str, tag: str = "info"):
        """Añadir mensaje al log"""
        self.log_text.config(state=tk.NORMAL)
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log_text.insert(tk.END, f"[{timestamp}] ", "info")
        self.log_text.insert(tk.END, f"{message}\n", tag)
        
        if self.autoscroll:
            self.log_text.see(tk.END)
        
        self.log_text.config(state=tk.DISABLED)
    
    def increment_count(self):
        """Incrementar contador de eventos"""
        self.event_count += 1
        self.event_count_var.set(f"Eventos: {self.event_count}")
    
    def clear(self):
        """Limpiar el log"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.event_count = 0
        self.event_count_var.set("Eventos: 0")


class ConnectionPanel(ttk.Frame):
    """Panel de conexión MIDI"""
    
    def __init__(self, parent, on_connect, on_disconnect, on_refresh):
        super().__init__(parent)
        
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self.on_refresh = on_refresh
        self.connected = False
        
        self._setup_ui()
    
    def _setup_ui(self):
        # Frame de conexión
        conn_frame = ttk.LabelFrame(self, text="Conexión MIDI", padding="10")
        conn_frame.pack(fill=tk.X)
        
        # Fila del selector
        select_frame = ttk.Frame(conn_frame)
        select_frame.pack(fill=tk.X)
        
        ttk.Label(select_frame, text="Puerto:").pack(side=tk.LEFT)
        
        # Combobox
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(
            select_frame,
            textvariable=self.port_var,
            state="readonly",
            width=45
        )
        self.port_combo.pack(side=tk.LEFT, padx=(10, 5), fill=tk.X, expand=True)
        
        # Botón refrescar
        self.refresh_btn = ttk.Button(
            select_frame,
            text="↻",
            width=3,
            command=self._on_refresh
        )
        self.refresh_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # Indicador
        self.indicator = tk.Canvas(select_frame, width=20, height=20, highlightthickness=0)
        self.indicator.pack(side=tk.LEFT)
        self.indicator_circle = self.indicator.create_oval(2, 2, 18, 18, fill="gray", outline="darkgray")
        
        # Fila de control
        control_frame = ttk.Frame(conn_frame)
        control_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.connect_btn = ttk.Button(
            control_frame,
            text="▶ Conectar",
            command=self._toggle_connection,
            width=15
        )
        self.connect_btn.pack(side=tk.LEFT)
        
        self.status_var = tk.StringVar(value="Desconectado")
        ttk.Label(control_frame, textvariable=self.status_var).pack(side=tk.LEFT, padx=(15, 0))
    
    def _on_refresh(self):
        ports = self.on_refresh()
        self.port_combo['values'] = ports
        if ports and not self.port_var.get():
            self.port_combo.current(0)
    
    def _toggle_connection(self):
        if self.connected:
            self.on_disconnect()
        else:
            port = self.port_var.get()
            if port:
                self.on_connect(port)
    
    def set_connected(self, connected: bool, port_name: str = None):
        """Actualizar estado de conexión"""
        self.connected = connected
        
        if connected:
            self.indicator.itemconfig(self.indicator_circle, fill="green")
            self.status_var.set(f"Conectado: {port_name}")
            self.connect_btn.config(text="■ Desconectar")
            self.port_combo.config(state="disabled")
            self.refresh_btn.config(state="disabled")
        else:
            self.indicator.itemconfig(self.indicator_circle, fill="gray")
            self.status_var.set("Desconectado")
            self.connect_btn.config(text="▶ Conectar")
            self.port_combo.config(state="readonly")
            self.refresh_btn.config(state="normal")
    
    def get_selected_port(self) -> str:
        return self.port_var.get()
