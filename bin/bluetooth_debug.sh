#!/bin/bash

# Script de diagnóstico detallado para Bluetooth
BT_MAC="E4:17:D8:04:73:D3"

echo "=== DIAGNÓSTICO BLUETOOTH ==="
echo ""

echo "1. Estado del controlador Bluetooth:"
bluetoothctl show | grep -E "Powered|Pairable|Discoverable"
echo ""

echo "2. Activando modo emparejable y descubrible..."
bluetoothctl pairable on
bluetoothctl discoverable on
echo ""

echo "3. Iniciando escaneo (10 segundos)..."
bluetoothctl scan on &
SCAN_PID=$!

for i in {10..1}; do
    echo -n "$i... "
    sleep 1
done
echo ""

echo "4. Deteniendo escaneo..."
bluetoothctl scan off
kill $SCAN_PID 2>/dev/null
echo ""

echo "5. Dispositivos detectados:"
bluetoothctl devices
echo ""

echo "6. Buscando dispositivo específico ($BT_MAC):"
if bluetoothctl devices | grep -q "$BT_MAC"; then
    echo "✓ DISPOSITIVO ENCONTRADO"
    echo ""
    echo "7. Información del dispositivo:"
    bluetoothctl info "$BT_MAC"
    echo ""
    
    echo "8. Intentando emparejar..."
    bluetoothctl pair "$BT_MAC"
    echo ""
    
    echo "9. Marcando como confiable..."
    bluetoothctl trust "$BT_MAC"
    echo ""
    
    echo "10. Conectando..."
    bluetoothctl connect "$BT_MAC"
    echo ""
    
    echo "11. Estado final del dispositivo:"
    bluetoothctl info "$BT_MAC"
    echo ""
    
    echo "12. Dispositivos de entrada creados:"
    ls -la /dev/input/js* 2>/dev/null || echo "No hay joysticks"
    ls -la /dev/input/event* | tail -5
    
else
    echo "✗ DISPOSITIVO NO ENCONTRADO"
    echo ""
    echo "Dispositivos cercanos detectados:"
    bluetoothctl devices | while read line; do
        echo "  - $line"
    done
    echo ""
    echo "POSIBLES CAUSAS:"
    echo "  - El dispositivo no está realmente en modo emparejamiento"
    echo "  - El dispositivo está demasiado lejos"
    echo "  - Interferencias de otros dispositivos"
    echo "  - El adaptador Bluetooth del sistema tiene problemas"
fi

echo ""
echo "=== FIN DIAGNÓSTICO ==="
