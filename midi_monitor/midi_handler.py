"""
Manejador de conexiones MIDI
"""

import threading
import queue
from typing import Callable, Optional, List

try:
    import mido
    MIDO_AVAILABLE = True
except ImportError:
    MIDO_AVAILABLE = False

from config import FILTERED_MESSAGES


class MidiHandler:
    """Gestiona la conexión y lectura de eventos MIDI"""
    
    def __init__(self):
        self.port: Optional[object] = None
        self.port_name: Optional[str] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.message_queue = queue.Queue()
        self.listeners: List[Callable] = []
    
    @staticmethod
    def is_available() -> bool:
        """Verificar si mido está disponible"""
        return MIDO_AVAILABLE
    
    @staticmethod
    def get_backend_name() -> str:
        """Obtener nombre del backend de mido"""
        if MIDO_AVAILABLE:
            return mido.backend.name
        return "No disponible"
    
    @staticmethod
    def get_input_ports() -> List[str]:
        """Obtener lista de puertos MIDI de entrada disponibles"""
        if not MIDO_AVAILABLE:
            return []
        try:
            return mido.get_input_names()
        except Exception:
            return []
    
    def add_listener(self, callback: Callable) -> None:
        """Añadir un listener para eventos MIDI"""
        if callback not in self.listeners:
            self.listeners.append(callback)
    
    def remove_listener(self, callback: Callable) -> None:
        """Eliminar un listener"""
        if callback in self.listeners:
            self.listeners.remove(callback)
    
    def connect(self, port_name: str) -> bool:
        """Conectar a un puerto MIDI"""
        if not MIDO_AVAILABLE:
            return False
        
        try:
            self.disconnect()
            self.port = mido.open_input(port_name)
            self.port_name = port_name
            self.running = True
            self.thread = threading.Thread(target=self._listen, daemon=True)
            self.thread.start()
            return True
        except Exception as e:
            self.port = None
            self.port_name = None
            raise e
    
    def disconnect(self) -> None:
        """Desconectar del puerto MIDI"""
        self.running = False
        
        if self.port:
            try:
                self.port.close()
            except:
                pass
            self.port = None
            self.port_name = None
    
    def is_connected(self) -> bool:
        """Verificar si está conectado"""
        return self.port is not None and self.running
    
    def _listen(self) -> None:
        """Hilo de escucha de eventos MIDI"""
        while self.running and self.port:
            try:
                for msg in self.port.iter_pending():
                    # Filtrar mensajes no deseados
                    if msg.type not in FILTERED_MESSAGES:
                        self.message_queue.put(msg)
                
                threading.Event().wait(0.001)
            except Exception:
                break
    
    def process_messages(self) -> None:
        """Procesar mensajes de la cola y notificar a los listeners"""
        try:
            while True:
                msg = self.message_queue.get_nowait()
                for listener in self.listeners:
                    try:
                        listener(msg)
                    except Exception:
                        pass
        except queue.Empty:
            pass


class MidiMessage:
    """Utilidades para formatear mensajes MIDI"""
    
    NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    
    @classmethod
    def note_name(cls, note_number: int) -> str:
        """Convertir número de nota MIDI a nombre"""
        octave = (note_number // 12) - 1
        note = cls.NOTE_NAMES[note_number % 12]
        return f"{note}{octave}"
    
    @classmethod
    def format_message(cls, msg) -> tuple:
        """Formatear un mensaje MIDI para mostrar. Retorna (texto, tag)"""
        if msg.type == 'note_on':
            text = f"NOTE ON  | Ch: {msg.channel:2d} | Nota: {msg.note:3d} ({cls.note_name(msg.note)}) | Vel: {msg.velocity:3d}"
            return text, "midi_note"
        
        elif msg.type == 'note_off':
            text = f"NOTE OFF | Ch: {msg.channel:2d} | Nota: {msg.note:3d} ({cls.note_name(msg.note)}) | Vel: {msg.velocity:3d}"
            return text, "midi_note"
        
        elif msg.type == 'control_change':
            text = f"CC       | Ch: {msg.channel:2d} | CC: {msg.control:3d} | Val: {msg.value:3d}"
            return text, "midi_cc"
        
        elif msg.type == 'program_change':
            text = f"PROGRAM  | Ch: {msg.channel:2d} | Prog: {msg.program:3d}"
            return text, "midi_cc"
        
        elif msg.type == 'pitchwheel':
            text = f"PITCH    | Ch: {msg.channel:2d} | Val: {msg.pitch}"
            return text, "midi_cc"
        
        elif msg.type == 'aftertouch':
            text = f"ATOUCH   | Ch: {msg.channel:2d} | Val: {msg.value:3d}"
            return text, "midi_other"
        
        elif msg.type == 'polytouch':
            text = f"PTOUCH   | Ch: {msg.channel:2d} | Nota: {msg.note:3d} | Val: {msg.value:3d}"
            return text, "midi_other"
        
        else:
            text = f"{msg.type.upper():8s} | {msg}"
            return text, "midi_other"
