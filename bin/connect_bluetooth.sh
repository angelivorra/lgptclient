#!/bin/bash

# Script para conectar el mando bluetooth 8BitDo
# MAC del dispositivo
BT_MAC="E4:17:D8:04:73:D3"

echo "Iniciando conexión Bluetooth..."

# Activar modo emparejable y descubrible
bluetoothctl pairable on >/dev/null 2>&1
bluetoothctl discoverable on >/dev/null 2>&1

# Iniciar escaneo en background
bluetoothctl scan on >/dev/null 2>&1 &
SCAN_PID=$!

# Esperar 10 segundos para detectar dispositivos (algunos dispositivos tardan más)
echo "Escaneando dispositivos..."
sleep 10

# Detener escaneo
bluetoothctl scan off >/dev/null 2>&1
kill $SCAN_PID 2>/dev/null
sleep 1

# Verificar si el dispositivo está disponible
if bluetoothctl devices | grep -q "$BT_MAC"; then
    echo "Dispositivo detectado"
    
    # Intentar emparejar (si no está emparejado)
    PAIR_OUTPUT=$(bluetoothctl pair "$BT_MAC" 2>&1)
    PAIR_RESULT=$?
    
    if [ $PAIR_RESULT -eq 0 ] || echo "$PAIR_OUTPUT" | grep -q "already exists"; then
        echo "Emparejamiento OK"
        
        # Marcar como confiable
        bluetoothctl trust "$BT_MAC" >/dev/null 2>&1
        echo "Dispositivo marcado como confiable"
        
        # Conectar
        CONNECT_OUTPUT=$(bluetoothctl connect "$BT_MAC" 2>&1)
        CONNECT_RESULT=$?
        
        if [ $CONNECT_RESULT -eq 0 ] || echo "$CONNECT_OUTPUT" | grep -q "Connection successful"; then
            echo "Conectado exitosamente"
            
            # Verificar que se creó el dispositivo de entrada
            sleep 2
            if grep -q "8BitDo" /proc/bus/input/devices 2>/dev/null; then
                echo "Dispositivo de entrada detectado correctamente"
                exit 0
            else
                echo "ADVERTENCIA: Conectado pero no se detecta dispositivo de entrada"
                exit 0
            fi
        else
            echo "ERROR: No se pudo conectar - $CONNECT_OUTPUT"
            exit 1
        fi
    else
        echo "ERROR: No se pudo emparejar - $PAIR_OUTPUT"
        exit 1
    fi
else
    echo "ERROR: Dispositivo no detectado. Asegúrate de que está en modo emparejamiento"
    exit 1
fi
