#!/usr/bin/env python3
"""
Script de test para GPIO con relés.

Activa un pin GPIO de forma repetitiva para probar su funcionamiento.
Incluye delay inicial opcional para permitir que el relé se estabilice
antes de activar la carga (útil para motores DC).

Uso:
    python3 test.py <pin> <duracion_ms> <pausa_ms> [delay_inicial_ms]

Ejemplos:
    python3 test.py 17 100 300
    python3 test.py 17 150 500 30
    
    Esto activará el GPIO 17:
    - HIGH
    - Espera delay_inicial_ms (si se especifica)
    - Activo durante duracion_ms
    - LOW
    - Pausa durante pausa_ms
    - Repetir hasta Ctrl+C
"""
import sys
import time
import signal

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("⚠️  RPi.GPIO no disponible - ejecutando en modo simulación")


def signal_handler(sig, frame):
    """Maneja Ctrl+C para salir limpiamente."""
    print("\n\n👋 Detenido por el usuario")
    print("🧹 Limpiando GPIO...")
    if GPIO_AVAILABLE:
        GPIO.cleanup()
    print("✅ GPIO limpiado")
    sys.exit(0)


def test_gpio(pin: int, duration_ms: int, pause_ms: int, initial_delay_ms: int = 0):
    """
    Test de GPIO con activaciones repetidas.
    
    Args:
        pin: Número de pin GPIO (BCM)
        duration_ms: Tiempo en HIGH en milisegundos
        pause_ms: Tiempo en LOW en milisegundos
        initial_delay_ms: Delay después de HIGH antes de contar duración (para relés)
    """
    duration_s = duration_ms / 1000.0
    pause_s = pause_ms / 1000.0
    initial_delay_s = initial_delay_ms / 1000.0
    
    print("=" * 60)
    print("Test de GPIO con Relés")
    print("=" * 60)
    print(f"Pin GPIO (BCM): {pin}")
    print(f"Duración HIGH: {duration_ms}ms ({duration_s:.3f}s)")
    print(f"Pausa LOW: {pause_ms}ms ({pause_s:.3f}s)")
    if initial_delay_ms > 0:
        print(f"Delay inicial: {initial_delay_ms}ms ({initial_delay_s:.3f}s)")
        print(f"  ⚡ Útil para permitir que el relé se estabilice antes de la carga")
    print(f"Modo: {'REAL' if GPIO_AVAILABLE else 'SIMULACIÓN'}")
    print(f"\nPresiona Ctrl+C para detener")
    print("=" * 60)
    print()
    
    # Configurar GPIO
    if GPIO_AVAILABLE:
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.LOW)
        print(f"✅ GPIO {pin} configurado como OUTPUT (LOW)")
    else:
        print(f"🔧 [SIM] GPIO {pin} configurado como OUTPUT (LOW)")
    
    print()
    print("Iniciando ciclo de activación...")
    print("-" * 60)
    print()
    
    # Registrar manejador de señal para Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    cycle = 0
    
    try:
        while True:
            cycle += 1
            start_time = time.time()
            
            # Activar (HIGH)
            if GPIO_AVAILABLE:
                GPIO.output(pin, GPIO.HIGH)
                if initial_delay_ms > 0:
                    print(f"🔌 Ciclo #{cycle}: Pin {pin} → HIGH")
                else:
                    print(f"🔌 Ciclo #{cycle}: Pin {pin} → HIGH (por {duration_ms}ms)")
            else:
                if initial_delay_ms > 0:
                    print(f"🔌 [SIM] Ciclo #{cycle}: Pin {pin} → HIGH")
                else:
                    print(f"🔌 [SIM] Ciclo #{cycle}: Pin {pin} → HIGH (por {duration_ms}ms)")
            
            # Delay inicial (para estabilización de relé)
            if initial_delay_ms > 0:
                print(f"   ⏱️  Esperando estabilización del relé: {initial_delay_ms}ms...")
                time.sleep(initial_delay_s)
                print(f"   ⚡ Carga activa por {duration_ms}ms")
            
            # Esperar duración
            time.sleep(duration_s)
            
            # Desactivar (LOW)
            if GPIO_AVAILABLE:
                GPIO.output(pin, GPIO.LOW)
            
            actual_duration = (time.time() - start_time) * 1000
            print(f"   Pin {pin} → LOW (estuvo {actual_duration:.1f}ms total)")
            
            # Pausa antes del siguiente ciclo
            print(f"   💤 Esperando {pause_ms}ms...")
            time.sleep(pause_s)
            
    except KeyboardInterrupt:
        # Este bloque no debería ejecutarse si signal_handler funciona
        # pero lo dejamos por si acaso
        signal_handler(None, None)


def main():
    """Punto de entrada principal."""
    if len(sys.argv) not in [4, 5]:
        print("❌ Error: Número incorrecto de argumentos")
        print()
        print("Uso:")
        print(f"    python3 {sys.argv[0]} <pin> <duracion_ms> <pausa_ms> [delay_inicial_ms]")
        print()
        print("Ejemplos:")
        print(f"    python3 {sys.argv[0]} 17 100 300")
        print(f"    python3 {sys.argv[0]} 17 150 500 30")
        print()
        print("Argumentos:")
        print("    pin              : Número de pin GPIO (modo BCM)")
        print("    duracion_ms      : Tiempo activo en milisegundos")
        print("    pausa_ms         : Tiempo en pausa en milisegundos")
        print("    delay_inicial_ms : (Opcional) Delay tras HIGH antes de contar duración")
        print()
        print("Descripción:")
        print("    Activa el pin GPIO de forma repetitiva:")
        print("    HIGH → [delay inicial] → espera duración → LOW → pausa → repetir")
        print()
        print("Delay inicial (útil para relés con motores):")
        print("    Permite que el relé se estabilice antes de que la carga se active.")
        print("    Valores típicos: 20-50ms")
        print()
        print("Para detener:")
        print("    Presiona Ctrl+C")
        print()
        sys.exit(1)
    
    try:
        pin = int(sys.argv[1])
        duration_ms = int(sys.argv[2])
        pause_ms = int(sys.argv[3])
        initial_delay_ms = int(sys.argv[4]) if len(sys.argv) == 5 else 0
    except ValueError as e:
        print(f"❌ Error: Los argumentos deben ser números enteros")
        print(f"   {e}")
        sys.exit(1)
    
    # Validaciones
    if pin < 0 or pin > 27:
        print(f"❌ Error: Pin {pin} fuera de rango (debe ser 0-27)")
        sys.exit(1)
    
    if duration_ms < 1:
        print(f"❌ Error: Duración debe ser mayor a 0ms")
        sys.exit(1)
    
    if pause_ms < 0:
        print(f"❌ Error: Pausa no puede ser negativa")
        sys.exit(1)
    
    if initial_delay_ms < 0:
        print(f"❌ Error: Delay inicial no puede ser negativo")
        sys.exit(1)
    
    # Ejecutar test
    test_gpio(pin, duration_ms, pause_ms, initial_delay_ms)


if __name__ == '__main__':
    main()
