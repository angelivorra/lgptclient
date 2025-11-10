#!/usr/bin/env python3
"""
Interfaz ncurses para Robotraca - Sistema de gestión de LGPT
"""

import curses
import importlib.util
import logging
import os
import sys
import time
import traceback
import subprocess
import threading
from typing import Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class ServiceStatus(Enum):
    """Estados de los servicios"""
    STOPPED = "Detenido"
    STARTING = "Iniciando..."
    RUNNING = "Activo"
    ERROR = "Error"


@dataclass
class SystemState:
    """Estado del sistema"""
    jackd_status: ServiceStatus = ServiceStatus.STOPPED
    alsa_in_status: ServiceStatus = ServiceStatus.STOPPED
    delay_buffer_status: ServiceStatus = ServiceStatus.STOPPED
    lgpt_status: ServiceStatus = ServiceStatus.STOPPED
    jackd_info: str = ""
    audio_connections: str = ""
    last_error: str = ""
    
    def all_audio_running(self) -> bool:
        """Verifica si toda la pila de audio está corriendo"""
        return (
            self.jackd_status == ServiceStatus.RUNNING and
            self.alsa_in_status == ServiceStatus.RUNNING and
            self.delay_buffer_status == ServiceStatus.RUNNING
        )


class RobotracaUI:
    """Interfaz ncurses para gestión de LGPT"""
    
    # Colores
    COLOR_TITLE = 1
    COLOR_RUNNING = 2
    COLOR_STOPPED = 3
    COLOR_ERROR = 4
    COLOR_BUTTON = 5
    COLOR_BUTTON_SELECTED = 6
    COLOR_INFO = 7
    
    # Opciones del menú
    MENU_RESTART_AUDIO = 0
    MENU_START_LGPT = 1
    MENU_EXIT = 2
    
    def __init__(self, stdscr, audio_manager):
        """
        Inicializa la UI
        
        Args:
            stdscr: Ventana principal de curses
            audio_manager: Instancia del gestor de audio (AudioStack)
        """
        self.stdscr = stdscr
        self.audio_manager = audio_manager
        self.state = SystemState()
        self.selected_menu = self.MENU_START_LGPT
        self.running = True
        self.status_thread = None
        self.gamepad_reader = None
        self.lock = threading.Lock()
        self.gamepad_event_queue = []  # Cola de eventos del gamepad
        
        # Configurar curses
        curses.curs_set(0)  # Ocultar cursor
        self.stdscr.nodelay(1)  # No bloquear en getch()
        self.stdscr.timeout(100)  # Timeout de 100ms
        
        # Inicializar colores
        self._init_colors()
        
        # Iniciar gamepad reader
        self._init_gamepad()
        
        # Iniciar thread de actualización de estado
        self.status_thread = threading.Thread(target=self._update_status_loop, daemon=True)
        self.status_thread.start()
    
    def _init_colors(self):
        """Inicializa los pares de colores para la UI"""
        curses.start_color()
        curses.use_default_colors()
        
        # Definir pares de colores
        curses.init_pair(self.COLOR_TITLE, curses.COLOR_CYAN, -1)
        curses.init_pair(self.COLOR_RUNNING, curses.COLOR_GREEN, -1)
        curses.init_pair(self.COLOR_STOPPED, curses.COLOR_YELLOW, -1)
        curses.init_pair(self.COLOR_ERROR, curses.COLOR_RED, -1)
        curses.init_pair(self.COLOR_BUTTON, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(self.COLOR_BUTTON_SELECTED, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(self.COLOR_INFO, curses.COLOR_WHITE, -1)
    
    def _init_gamepad(self):
        """Inicializa el lector de gamepad"""
        try:
            from gamepad_reader import GamepadReader
            
            # Callback para eventos del gamepad
            def gamepad_callback(event_type: str):
                # Agregar evento a la cola para procesarlo en el thread principal
                self.gamepad_event_queue.append(event_type)
            
            self.gamepad_reader = GamepadReader(callback=gamepad_callback)
            if self.gamepad_reader.start():
                import logging
                logging.info("Gamepad USB detectado y activo")
            else:
                import logging
                logging.info("Gamepad no disponible, usando solo teclado")
                self.gamepad_reader = None
        except Exception as e:
            import logging
            logging.warning(f"No se pudo inicializar gamepad: {e}")
            self.gamepad_reader = None
    
    def _update_status_loop(self):
        """Loop que actualiza el estado del sistema continuamente"""
        while self.running:
            try:
                self._update_system_status()
                time.sleep(0.5)  # Actualizar cada 500ms
            except Exception:
                pass
    
    def _update_system_status(self):
        """Actualiza el estado de todos los servicios"""
        with self.lock:
            # Verificar jackd
            self.state.jackd_status = self._check_process_status("jackd")
            if self.state.jackd_status == ServiceStatus.RUNNING:
                self.state.jackd_info = self._get_jack_info()
            
            # Verificar alsa_in
            self.state.alsa_in_status = self._check_process_status("alsa_in")
            
            # Verificar delay_buffer
            if self._check_jack_client("delay_buffer"):
                self.state.delay_buffer_status = ServiceStatus.RUNNING
            else:
                self.state.delay_buffer_status = ServiceStatus.STOPPED
            
            # Verificar LGPT
            self.state.lgpt_status = self._check_process_status("lgpt.rpi-exe")
            
            # Obtener conexiones de audio
            if self.state.jackd_status == ServiceStatus.RUNNING:
                self.state.audio_connections = self._get_audio_connections()
    
    def _check_process_status(self, process_name: str) -> ServiceStatus:
        """Verifica si un proceso está corriendo"""
        try:
            result = subprocess.run(
                ["pgrep", "-x", process_name],
                capture_output=True,
                timeout=1.0
            )
            return ServiceStatus.RUNNING if result.returncode == 0 else ServiceStatus.STOPPED
        except Exception:
            return ServiceStatus.STOPPED
    
    def _check_jack_client(self, client_name: str) -> bool:
        """Verifica si un cliente JACK existe"""
        try:
            result = subprocess.run(
                ["jack_lsp"],
                capture_output=True,
                text=True,
                timeout=1.0
            )
            if result.returncode == 0:
                return f"{client_name}:" in result.stdout
        except Exception:
            pass
        return False
    
    def _get_jack_info(self) -> str:
        """Obtiene información de JACK"""
        try:
            result = subprocess.run(
                ["jack_samplerate"],
                capture_output=True,
                text=True,
                timeout=1.0
            )
            if result.returncode == 0:
                samplerate = result.stdout.strip()
                
                result2 = subprocess.run(
                    ["jack_bufsize"],
                    capture_output=True,
                    text=True,
                    timeout=1.0
                )
                if result2.returncode == 0:
                    bufsize = result2.stdout.strip()
                    return f"{samplerate}Hz / {bufsize} frames"
        except Exception:
            pass
        return "Información no disponible"
    
    def _get_audio_connections(self) -> str:
        """Obtiene las conexiones de audio activas"""
        try:
            result = subprocess.run(
                ["jack_lsp", "-c"],
                capture_output=True,
                text=True,
                timeout=1.0
            )
            if result.returncode == 0:
                # Contar conexiones relevantes
                lines = result.stdout.split('\n')
                lgpt_connections = sum(1 for line in lines if 'LGPT:capture' in line and '   ' in line)
                delay_connections = sum(1 for line in lines if 'delay_buffer' in line and '   ' in line)
                return f"LGPT: {lgpt_connections} | Delay: {delay_connections}"
        except Exception:
            pass
        return "N/A"
    
    def _get_status_color(self, status: ServiceStatus) -> int:
        """Obtiene el color para un estado"""
        if status == ServiceStatus.RUNNING:
            return self.COLOR_RUNNING
        elif status == ServiceStatus.ERROR:
            return self.COLOR_ERROR
        elif status == ServiceStatus.STARTING:
            return self.COLOR_INFO
        else:
            return self.COLOR_STOPPED
    
    def _draw_box(self, y: int, x: int, height: int, width: int, title: str = ""):
        """Dibuja una caja con borde"""
        # Bordes
        self.stdscr.addch(y, x, curses.ACS_ULCORNER)
        self.stdscr.addch(y, x + width - 1, curses.ACS_URCORNER)
        self.stdscr.addch(y + height - 1, x, curses.ACS_LLCORNER)
        self.stdscr.addch(y + height - 1, x + width - 1, curses.ACS_LRCORNER)
        
        for i in range(1, width - 1):
            self.stdscr.addch(y, x + i, curses.ACS_HLINE)
            self.stdscr.addch(y + height - 1, x + i, curses.ACS_HLINE)
        
        for i in range(1, height - 1):
            self.stdscr.addch(y + i, x, curses.ACS_VLINE)
            self.stdscr.addch(y + i, x + width - 1, curses.ACS_VLINE)
        
        # Título
        if title:
            title_str = f" {title} "
            title_x = x + (width - len(title_str)) // 2
            self.stdscr.addstr(y, title_x, title_str, curses.color_pair(self.COLOR_TITLE) | curses.A_BOLD)
    
    def _show_progress_dialog(self, title: str, message: str, show_spinner: bool = True):
        """Muestra un diálogo de progreso modal"""
        height, width = self.stdscr.getmaxyx()
        
        # Dimensiones del diálogo
        dialog_width = min(60, width - 4)
        dialog_height = 8
        dialog_y = (height - dialog_height) // 2
        dialog_x = (width - dialog_width) // 2
        
        # Limpiar área del diálogo
        for i in range(dialog_height):
            self.stdscr.addstr(dialog_y + i, dialog_x, " " * dialog_width)
        
        # Dibujar caja
        self._draw_box(dialog_y, dialog_x, dialog_height, dialog_width, title)
        
        # Mensaje
        msg_lines = []
        if len(message) > dialog_width - 6:
            # Dividir en líneas
            words = message.split()
            current_line = ""
            for word in words:
                if len(current_line) + len(word) + 1 <= dialog_width - 6:
                    current_line += word + " "
                else:
                    msg_lines.append(current_line.strip())
                    current_line = word + " "
            if current_line:
                msg_lines.append(current_line.strip())
        else:
            msg_lines = [message]
        
        # Dibujar mensaje centrado
        start_y = dialog_y + 2
        for i, line in enumerate(msg_lines[:3]):  # Máximo 3 líneas
            msg_x = dialog_x + (dialog_width - len(line)) // 2
            self.stdscr.addstr(start_y + i, msg_x, line, curses.color_pair(self.COLOR_INFO))
        
        # Spinner animado
        if show_spinner:
            spinner_y = dialog_y + dialog_height - 3
            spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
            spinner_idx = int(time.time() * 10) % len(spinner_chars)
            spinner_text = f"  {spinner_chars[spinner_idx]}  "
            spinner_x = dialog_x + (dialog_width - len(spinner_text)) // 2
            self.stdscr.addstr(spinner_y, spinner_x, spinner_text, 
                             curses.color_pair(self.COLOR_TITLE) | curses.A_BOLD)
        
        self.stdscr.refresh()
    
    def _show_error_dialog(self, title: str, message: str, wait_for_input: bool = True):
        """Muestra un diálogo de error modal con fondo sólido"""
        height, width = self.stdscr.getmaxyx()
        
        # Dimensiones del diálogo
        dialog_width = min(70, width - 4)
        dialog_height = 12
        dialog_y = (height - dialog_height) // 2
        dialog_x = (width - dialog_width) // 2
        
        # Limpiar completamente y redibujar fondo
        self.stdscr.erase()
        self.draw()
        
        # Dibujar fondo semi-oscuro detrás del diálogo para mejor contraste
        # Llenar toda el área del diálogo con espacios (fondo sólido)
        for row in range(dialog_height):
            try:
                self.stdscr.addstr(dialog_y + row, dialog_x, " " * dialog_width, 
                                 curses.color_pair(self.COLOR_INFO))
            except curses.error:
                pass
        
        # Dibujar caja de error
        self._draw_box(dialog_y, dialog_x, dialog_height, dialog_width, title)
        
        # Icono de error
        error_icon = "⚠"
        icon_x = dialog_x + (dialog_width - len(error_icon)) // 2
        self.stdscr.addstr(dialog_y + 2, icon_x, error_icon, 
                         curses.color_pair(self.COLOR_ERROR) | curses.A_BOLD)
        
        # Mensaje de error (dividido en líneas)
        msg_lines = []
        max_line_width = dialog_width - 8
        words = message.split()
        current_line = ""
        for word in words:
            if len(current_line) + len(word) + 1 <= max_line_width:
                current_line += word + " "
            else:
                msg_lines.append(current_line.strip())
                current_line = word + " "
        if current_line:
            msg_lines.append(current_line.strip())
        
        # Dibujar mensaje
        start_y = dialog_y + 4
        for i, line in enumerate(msg_lines[:5]):  # Máximo 5 líneas
            msg_x = dialog_x + 4
            self.stdscr.addstr(start_y + i, msg_x, line, curses.color_pair(self.COLOR_ERROR))
        
        # Instrucción
        if wait_for_input:
            instruction = "Presiona cualquier botón para continuar..."
            instr_x = dialog_x + (dialog_width - len(instruction)) // 2
            self.stdscr.addstr(dialog_y + dialog_height - 2, instr_x, instruction, 
                             curses.color_pair(self.COLOR_INFO) | curses.A_DIM)
        
        self.stdscr.refresh()
        
        if wait_for_input:
            # Esperar entrada del usuario (teclado o gamepad)
            # Mantener modo no-bloqueante para poder verificar el gamepad
            logging.info("[ERROR_DIALOG] Esperando entrada de usuario...")
            logging.info(f"[ERROR_DIALOG] Gamepad reader activo: {self.gamepad_reader is not None}")
            if self.gamepad_reader:
                logging.info(f"[ERROR_DIALOG] Gamepad running: {self.gamepad_reader.running}")
            
            iteration = 0
            while True:
                iteration += 1
                
                # Verificar gamepad primero
                try:
                    queue_size = self.gamepad_event_queue.qsize()
                    if iteration % 20 == 0:  # Log cada segundo aprox
                        logging.info(f"[ERROR_DIALOG] Iteración {iteration}, cola gamepad: {queue_size} eventos")
                    
                    if not self.gamepad_event_queue.empty():
                        logging.info(f"[ERROR_DIALOG] ¡Evento de gamepad detectado! Limpiando cola...")
                        # Limpiar la cola completa
                        while not self.gamepad_event_queue.empty():
                            try:
                                event = self.gamepad_event_queue.get_nowait()
                                logging.info(f"[ERROR_DIALOG] Evento removido de cola: {event}")
                            except:
                                break
                        logging.info("[ERROR_DIALOG] Saliendo del diálogo por evento de gamepad")
                        break
                except Exception as e:
                    logging.error(f"[ERROR_DIALOG] Error verificando gamepad: {e}")
                
                # Verificar teclado
                key = self.stdscr.getch()
                if key != -1:
                    logging.info(f"[ERROR_DIALOG] Tecla presionada: {key}. Saliendo del diálogo")
                    break
                
                time.sleep(0.05)
    
    def _draw_status_line(self, y: int, x: int, label: str, status: ServiceStatus, info: str = ""):
        """Dibuja una línea de estado de servicio"""
        # Label
        self.stdscr.addstr(y, x, label.ljust(16), curses.color_pair(self.COLOR_INFO))
        
        # Status
        status_color = self._get_status_color(status)
        status_str = f"[{status.value}]".ljust(14)
        self.stdscr.addstr(y, x + 17, status_str, curses.color_pair(status_color) | curses.A_BOLD)
        
        # Info adicional
        if info:
            max_info_width = 35
            info_truncated = info[:max_info_width]
            self.stdscr.addstr(y, x + 32, info_truncated, curses.color_pair(self.COLOR_INFO))
    
    def _draw_button(self, y: int, x: int, label: str, selected: bool, width: int = 30):
        """Dibuja un botón"""
        color = self.COLOR_BUTTON_SELECTED if selected else self.COLOR_BUTTON
        button_text = label.center(width)
        
        try:
            self.stdscr.addstr(y, x, button_text, curses.color_pair(color) | curses.A_BOLD)
        except curses.error:
            pass
    
    def draw(self):
        """Dibuja la interfaz completa"""
        # Usar erase() en lugar de clear() para evitar parpadeo
        self.stdscr.erase()
        height, width = self.stdscr.getmaxyx()
        
        # Verificar tamaño mínimo
        if height < 24 or width < 80:
            self.stdscr.addstr(0, 0, "Terminal muy pequeña. Mínimo: 80x24", curses.color_pair(self.COLOR_ERROR))
            self.stdscr.refresh()
            return
        
        with self.lock:
            # Título principal
            title = "╔═══════════════════════════════════════╗"
            title2 = "║         R O B O T R A C A            ║"
            title3 = "╚═══════════════════════════════════════╝"
            
            start_x = (width - len(title)) // 2
            self.stdscr.addstr(1, start_x, title, curses.color_pair(self.COLOR_TITLE) | curses.A_BOLD)
            self.stdscr.addstr(2, start_x, title2, curses.color_pair(self.COLOR_TITLE) | curses.A_BOLD)
            self.stdscr.addstr(3, start_x, title3, curses.color_pair(self.COLOR_TITLE) | curses.A_BOLD)
            
            # Subtítulo
            subtitle = "Sistema de Gestión LGPT"
            self.stdscr.addstr(4, (width - len(subtitle)) // 2, subtitle, curses.color_pair(self.COLOR_INFO))
            
            # Sección de estado de servicios
            box_y = 6
            box_x = 3
            box_width = width - 6
            box_height = 10
            
            self._draw_box(box_y, box_x, box_height, box_width, "Estado de Servicios")
            
            content_y = box_y + 2
            content_x = box_x + 3
            
            self._draw_status_line(content_y, content_x, "JACK Server:", self.state.jackd_status, self.state.jackd_info)
            self._draw_status_line(content_y + 1, content_x, "ALSA Input:", self.state.alsa_in_status)
            self._draw_status_line(content_y + 2, content_x, "Delay Buffer:", self.state.delay_buffer_status)
            self._draw_status_line(content_y + 4, content_x, "LGPT Tracker:", self.state.lgpt_status)
            
            # Conexiones de audio
            if self.state.audio_connections:
                self.stdscr.addstr(content_y + 6, content_x, f"Conexiones: {self.state.audio_connections}", 
                                 curses.color_pair(self.COLOR_INFO))
            
            # Sección de controles
            controls_y = box_y + box_height + 2
            controls_x = box_x
            controls_width = box_width
            controls_height = 8
            
            self._draw_box(controls_y, controls_x, controls_height, controls_width, "Controles")
            
            button_y = controls_y + 2
            button_x = (width - 30) // 2
            
            # Botones
            self._draw_button(button_y, button_x, "Reiniciar Sistema Audio", 
                            self.selected_menu == self.MENU_RESTART_AUDIO)
            
            # Botón LGPT - habilitado solo si el audio está OK
            lgpt_label = "Iniciar LGPT"
            if self.state.lgpt_status == ServiceStatus.RUNNING:
                lgpt_label = "LGPT Ejecutándose..."
            elif not self.state.all_audio_running():
                lgpt_label = "Iniciar LGPT (Audio no listo)"
            
            self._draw_button(button_y + 2, button_x, lgpt_label,
                            self.selected_menu == self.MENU_START_LGPT)
            
            self._draw_button(button_y + 4, button_x, "Salir",
                            self.selected_menu == self.MENU_EXIT)
            
            # Información de ayuda
            help_y = height - 3
            help_text = "↑/↓: Navegar  |  ENTER: Seleccionar  |  C: Limpiar error  |  Q: Salir"
            self.stdscr.addstr(help_y, (width - len(help_text)) // 2, help_text, 
                             curses.color_pair(self.COLOR_INFO) | curses.A_DIM)
            
            # Errores si hay (con fondo para mayor visibilidad)
            if self.state.last_error:
                error_y = height - 2
                error_text = f" ⚠ ERROR: {self.state.last_error[:width-20]} "
                # Centrar el error
                error_x = max(3, (width - len(error_text)) // 2)
                try:
                    # Dibujar con fondo rojo
                    self.stdscr.addstr(error_y, error_x, error_text, 
                                     curses.color_pair(self.COLOR_ERROR) | curses.A_BOLD | curses.A_REVERSE)
                except curses.error:
                    # Si falla, intentar sin formato especial
                    try:
                        self.stdscr.addstr(error_y, 3, error_text[:width-6], 
                                         curses.color_pair(self.COLOR_ERROR))
                    except curses.error:
                        pass
        
        self.stdscr.refresh()
    
    def handle_input(self) -> bool:
        """
        Maneja la entrada del usuario (teclado y gamepad)
        
        Returns:
            False si se debe salir, True para continuar
        """
        # Procesar eventos del gamepad primero
        while self.gamepad_event_queue:
            gamepad_event = self.gamepad_event_queue.pop(0)
            if not self._handle_gamepad_event(gamepad_event):
                return False
        
        # Procesar entrada de teclado
        try:
            key = self.stdscr.getch()
            
            if key == -1:  # No hay tecla
                return True
            
            # Teclas de navegación
            if key == curses.KEY_UP or key == ord('k'):
                self.selected_menu = (self.selected_menu - 1) % 3
            elif key == curses.KEY_DOWN or key == ord('j'):
                self.selected_menu = (self.selected_menu + 1) % 3
            
            # Tecla para limpiar error
            elif key == ord('c') or key == ord('C'):
                with self.lock:
                    self.state.last_error = ""
            
            # Tecla de salida rápida
            elif key == ord('q') or key == ord('Q'):
                return False
            
            # Enter - ejecutar acción
            elif key == ord('\n') or key == curses.KEY_ENTER or key == 10 or key == 13:
                return self._execute_menu_action()
        
        except KeyboardInterrupt:
            return False
        
        return True
    
    def _handle_gamepad_event(self, event_type: str) -> bool:
        """
        Maneja eventos del gamepad
        
        Args:
            event_type: Tipo de evento ('up', 'down', 'select', etc.)
        
        Returns:
            False si se debe salir, True para continuar
        """
        if event_type == 'up':
            self.selected_menu = (self.selected_menu - 1) % 3
        elif event_type == 'down':
            self.selected_menu = (self.selected_menu + 1) % 3
        elif event_type == 'select':
            # Botón de acción (A, B, o trigger)
            return self._execute_menu_action()
        elif event_type == 'start':
            # Start podría ser para salir o menú
            return False
        elif event_type == 'back':
            # Select/Back para salir
            return False
        
        return True
    
    def _execute_menu_action(self) -> bool:
        """Ejecuta la acción del menú seleccionado"""
        if self.selected_menu == self.MENU_EXIT:
            return False
        
        elif self.selected_menu == self.MENU_RESTART_AUDIO:
            self._restart_audio_system()
        
        elif self.selected_menu == self.MENU_START_LGPT:
            # Solo permitir si el audio está listo y LGPT no está corriendo
            if self.state.lgpt_status == ServiceStatus.RUNNING:
                self.state.last_error = "LGPT ya está ejecutándose"
            elif not self.state.all_audio_running():
                self.state.last_error = "Sistema de audio no está listo"
            else:
                self._start_lgpt()
        
        return True
    
    def _restart_audio_system(self):
        """Reinicia el sistema de audio con diálogo de progreso"""
        # Crear variable compartida para el estado
        restart_status = {'done': False, 'success': False, 'error': None}
        
        with self.lock:
            self.state.last_error = ""
            self.state.jackd_status = ServiceStatus.STARTING
            self.state.alsa_in_status = ServiceStatus.STARTING
            self.state.delay_buffer_status = ServiceStatus.STARTING
        
        # Ejecutar en thread
        def restart_thread():
            try:
                # Detener stack actual
                self.audio_manager.stop()
                time.sleep(1)
                
                # Reiniciar stack
                success = self.audio_manager.start()
                
                restart_status['success'] = success
                if not success:
                    restart_status['error'] = "Error al reiniciar sistema de audio"
                    with self.lock:
                        self.state.jackd_status = ServiceStatus.ERROR
                
            except Exception as e:
                restart_status['success'] = False
                restart_status['error'] = f"Error: {str(e)}"
                with self.lock:
                    self.state.jackd_status = ServiceStatus.ERROR
            finally:
                restart_status['done'] = True
        
        thread = threading.Thread(target=restart_thread, daemon=True)
        thread.start()
        
        # Mostrar diálogo de progreso mientras se reinicia
        start_time = time.time()
        while not restart_status['done']:
            elapsed = time.time() - start_time
            if elapsed < 5:
                self._show_progress_dialog("Reiniciando Audio", "Deteniendo servicios...", True)
            elif elapsed < 10:
                self._show_progress_dialog("Reiniciando Audio", "Iniciando JACK...", True)
            else:
                self._show_progress_dialog("Reiniciando Audio", "Configurando audio...", True)
            
            time.sleep(0.1)
        
        # Mostrar resultado
        if not restart_status['success']:
            error_msg = restart_status.get('error', 'Error desconocido')
            self._show_error_dialog("Error al Reiniciar Audio", error_msg, wait_for_input=True)
            with self.lock:
                self.state.last_error = error_msg[:70]
        else:
            # Mostrar mensaje de éxito brevemente
            self._show_progress_dialog("Audio Reiniciado", "✓ Sistema de audio listo", False)
            time.sleep(1)
    
    def _start_lgpt(self):
        """Inicia LGPT con diálogo de progreso y errores"""
        with self.lock:
            self.state.last_error = ""
            self.state.lgpt_status = ServiceStatus.STARTING
        
        # Mostrar diálogo de carga
        self._show_progress_dialog("Iniciando LGPT", "Cargando LGPT Tracker...", True)
        time.sleep(0.5)
        
        # Preparar ejecución
        error_msg = None
        run_lgpt = None
        
        try:
            # Importar la función de ejecución de LGPT
            script_dir = os.path.dirname(os.path.abspath(__file__))
            if script_dir not in sys.path:
                sys.path.insert(0, script_dir)
            
            lgpt_script_path = os.path.join(script_dir, "run-lgpt.py")
            
            # Verificar que el archivo existe
            if not os.path.exists(lgpt_script_path):
                raise FileNotFoundError(f"No se encontró run-lgpt.py en {script_dir}")
            
            # Importar el módulo
            import importlib.util
            spec = importlib.util.spec_from_file_location("run_lgpt", lgpt_script_path)
            
            if spec is None:
                raise ImportError(f"No se pudo crear spec para {lgpt_script_path}")
            
            if spec.loader is None:
                raise ImportError(f"spec.loader es None para {lgpt_script_path}")
            
            run_lgpt = importlib.util.module_from_spec(spec)
            
            if run_lgpt is None:
                raise ImportError("module_from_spec retornó None")
            
            # Ejecutar el módulo
            logging.info(f"[LGPT_START] Ejecutando módulo run-lgpt.py...")
            logging.info(f"[LGPT_START] run_lgpt type: {type(run_lgpt)}")
            logging.info(f"[LGPT_START] run_lgpt.__dict__ exists: {hasattr(run_lgpt, '__dict__')}")
            
            try:
                spec.loader.exec_module(run_lgpt)
                logging.info(f"[LGPT_START] Módulo ejecutado exitosamente")
            except Exception as exec_err:
                logging.error(f"[LGPT_START] Error en exec_module: {exec_err}")
                logging.error(f"[LGPT_START] Traceback:\n{traceback.format_exc()}")
                raise ImportError(f"Error ejecutando módulo run-lgpt.py: {exec_err}")
            
            # Verificar que tiene los atributos necesarios
            if not hasattr(run_lgpt, 'run_lgpt_process'):
                raise AttributeError("run_lgpt no tiene atributo 'run_lgpt_process'")
            
            if not hasattr(run_lgpt, 'LGPT_EXECUTABLE'):
                raise AttributeError("run_lgpt no tiene atributo 'LGPT_EXECUTABLE'")
            
            lgpt_path = run_lgpt.LGPT_EXECUTABLE
            if not lgpt_path:
                raise ValueError("LGPT_EXECUTABLE está vacío")
            
            # Guardar estado del terminal y salir de curses temporalmente
            curses.def_prog_mode()
            curses.endwin()
            
            # Ejecutar LGPT (bloqueante)
            try:
                run_lgpt.run_lgpt_process(lgpt_path)
            except Exception as exec_error:
                # Restaurar curses primero para poder mostrar el error
                curses.reset_prog_mode()
                self.stdscr.erase()
                self.stdscr.refresh()
                # Re-lanzar para capturar en el catch externo
                raise RuntimeError(f"Error ejecutando LGPT: {exec_error}")
            
            # Si llegamos aquí, LGPT terminó exitosamente
            curses.reset_prog_mode()
            self.stdscr.erase()
            self.stdscr.refresh()
            
        except (AttributeError, ImportError, ValueError, RuntimeError) as e:
            error_msg = str(e)
            tb = traceback.format_exc()
            logging.error(f"Error iniciando LGPT: {error_msg}")
            logging.error(f"Traceback completo:\n{tb}")
            # Añadir info del traceback al mensaje de error
            tb_lines = tb.split('\n')
            # Buscar la línea con "File" para mostrar dónde ocurrió
            file_line = ""
            for line in tb_lines:
                if 'File "' in line and 'line' in line:
                    file_line = line.strip()
            if file_line:
                error_msg = f"{error_msg}\n\n{file_line}"
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            tb = traceback.format_exc()
            logging.error(f"Error ejecutando LGPT: {error_msg}")
            logging.error(f"Traceback completo:\n{tb}")
            # Añadir info del traceback al mensaje de error
            tb_lines = tb.split('\n')
            file_line = ""
            for line in tb_lines:
                if 'File "' in line and 'line' in line:
                    file_line = line.strip()
            if file_line:
                error_msg = f"{error_msg}\n\n{file_line}"
        finally:
            with self.lock:
                self.state.lgpt_status = ServiceStatus.STOPPED
            
            # Si hubo error, mostrarlo
            if error_msg:
                with self.lock:
                    self.state.last_error = error_msg[:70]
                self._show_error_dialog("Error al Iniciar LGPT", error_msg, wait_for_input=True)
    
    def run(self):
        """Loop principal de la UI"""
        try:
            while self.running:
                try:
                    self.draw()
                    if not self.handle_input():
                        break
                except Exception as e:
                    # Capturar errores en el loop pero no crashear
                    import logging
                    logging.error(f"Error en UI loop: {e}")
                    with self.lock:
                        self.state.last_error = f"Error UI: {str(e)[:50]}"
                    time.sleep(0.5)  # Esperar un poco antes de continuar
                
                time.sleep(0.05)  # 50ms entre frames
        finally:
            # Cleanup
            self.running = False
            if self.gamepad_reader:
                try:
                    self.gamepad_reader.stop()
                except Exception:
                    pass


def run_ui(audio_manager):
    """
    Función principal para ejecutar la UI
    
    Args:
        audio_manager: Instancia del AudioStack
    """
    def _curses_main(stdscr):
        ui = RobotracaUI(stdscr, audio_manager)
        ui.run()
    
    curses.wrapper(_curses_main)
