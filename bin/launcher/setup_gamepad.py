#!/usr/bin/env python3
"""
Script para capturar y mapear botones del gamepad.
Te pedirá que presiones cada botón específico y guardará la configuración.
"""

import sys
import time
import json

try:
    import evdev
except ImportError:
    print("ERROR: evdev no está instalado")
    print("Instálalo con: pip install evdev")
    sys.exit(1)


def find_gamepad():
    """Busca y retorna el dispositivo gamepad"""
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    
    # Buscar gamepad
    for dev in devices:
        if 'gamepad' in dev.name.lower() or 'joystick' in dev.name.lower():
            return dev
    
    # Si no encontramos por nombre, usar el primero disponible
    if devices:
        return devices[0]
    
    return None


def wait_for_event(device, timeout=10, is_button_action=False):
    """
    Espera a que se presione un botón o se mueva un eje.
    Retorna el evento capturado.
    
    Args:
        is_button_action: Si True, solo captura botones (no ejes)
    """
    print("   Esperando entrada... ", end='', flush=True)
    
    start_time = time.time()
    captured_events = []
    last_axis_values = {}  # Para detectar cambios reales
    
    try:
        # Capturar eventos durante un breve período
        while time.time() - start_time < timeout:
            event = device.read_one()
            if event:
                # Filtrar solo eventos de botones (EV_KEY) y ejes (EV_ABS)
                if event.type == evdev.ecodes.EV_KEY and event.value == 1:
                    # Botón presionado
                    captured_events.append({
                        'type': 'button',
                        'code': event.code,
                        'name': evdev.ecodes.KEY[event.code] if event.code in evdev.ecodes.KEY else f"BTN_{event.code}"
                    })
                    print(f"✓ Botón detectado: {captured_events[-1]['name']} (code={event.code})")
                    time.sleep(0.3)  # Esperar un poco para evitar rebotes
                    return captured_events[-1]
                
                elif event.type == evdev.ecodes.EV_ABS and not is_button_action:
                    # Movimiento de eje (D-pad o joystick)
                    axis_name = evdev.ecodes.ABS[event.code] if event.code in evdev.ecodes.ABS else f"ABS_{event.code}"
                    
                    # Obtener valor previo
                    prev_value = last_axis_values.get(event.code, 128)  # 128 es típicamente neutral
                    last_axis_values[event.code] = event.value
                    
                    # Solo capturar si hay un cambio DESDE neutral HACIA una dirección
                    # Ignorar valores neutros/centrales (típicamente 127-129)
                    is_neutral = 126 <= event.value <= 130
                    was_neutral = 126 <= prev_value <= 130
                    
                    # Solo capturar cuando nos movemos DESDE neutral hacia alguna dirección
                    if was_neutral and not is_neutral:
                        captured_events.append({
                            'type': 'axis',
                            'code': event.code,
                            'value': event.value,
                            'name': axis_name
                        })
                        print(f"✓ Eje detectado: {axis_name} = {event.value} (code={event.code})")
                        time.sleep(0.5)  # Esperar más tiempo para evitar capturar el retorno
                        
                        # Limpiar eventos pendientes
                        while device.read_one():
                            pass
                        
                        return captured_events[-1]
            
            time.sleep(0.01)
    
    except KeyboardInterrupt:
        print("\n\n❌ Cancelado por el usuario")
        return None
    
    print("⏱ Timeout")
    return None


def main():
    print("="*60)
    print("  CONFIGURADOR DE GAMEPAD PARA ROBOTRACA")
    print("="*60)
    print()
    
    # Encontrar gamepad
    print("🎮 Buscando gamepad...")
    device = find_gamepad()
    
    if not device:
        print("❌ No se encontró ningún gamepad conectado")
        print("   Conecta el gamepad USB y vuelve a intentar")
        sys.exit(1)
    
    print(f"✓ Gamepad encontrado: {device.name}")
    print(f"  Dispositivo: {device.path}")
    print()
    
    # Configuración a capturar
    config = {
        'device_name': device.name,
        'device_path': device.path,
        'mappings': {}
    }
    
    # Lista de acciones a mapear
    actions = [
        ('up', 'ARRIBA (↑)', 'Mueve el D-pad/joystick hacia ARRIBA', False),
        ('down', 'ABAJO (↓)', 'Mueve el D-pad/joystick hacia ABAJO', False),
        ('select', 'ACEPTAR/ACCIÓN', 'Presiona el botón de ACEPTAR (A, B, o cualquier botón de acción)', True),
    ]
    
    print("Vamos a mapear 3 acciones:")
    print()
    
    for action_key, action_name, action_desc, is_button in actions:
        print(f"📌 Acción: {action_name}")
        print(f"   {action_desc}")
        
        # Para botones, esperar solo eventos de botones (no ejes)
        event = wait_for_event(device, timeout=15, is_button_action=is_button)
        
        if event is None:
            print("❌ No se detectó ninguna entrada. Abortando...")
            sys.exit(1)
        
        config['mappings'][action_key] = event
        print()
    
    print("="*60)
    print("✅ CONFIGURACIÓN COMPLETADA")
    print("="*60)
    print()
    print("Resumen de la configuración:")
    print()
    
    for action in ['up', 'down', 'select']:
        mapping = config['mappings'][action]
        if mapping['type'] == 'button':
            print(f"  {action.upper():8} → Botón: {mapping['name']} (code={mapping['code']})")
        else:
            print(f"  {action.upper():8} → Eje: {mapping['name']} = {mapping['value']} (code={mapping['code']})")
    
    print()
    
    # Guardar configuración
    config_file = '/home/angel/lgptclient/bin/launcher/gamepad_config.json'
    try:
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"💾 Configuración guardada en: {config_file}")
        print()
        print("✓ Ahora puedes usar el gamepad con Robotraca")
    except Exception as e:
        print(f"❌ Error guardando configuración: {e}")
        print()
        print("Configuración en JSON (copia manualmente si es necesario):")
        print(json.dumps(config, indent=2))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Proceso cancelado")
        sys.exit(1)
