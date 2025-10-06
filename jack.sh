#!/bin/bash

echo "Testing JACK with IQaudIO DAC..."

# Variable necesaria para modo headless (sin X11)
export JACK_NO_AUDIO_RESERVATION=1

# Parar JACK si está corriendo
killall -9 jackd 2>/dev/null
sleep 1

# Arrancar JACK a 44100Hz
jackd -R -P70 -dalsa -dhw:IQaudIODAC -r44100 -p256 -n3 &
JACK_PID=$!

sleep 3

# Verificar puertos
echo "Available JACK ports:"
jack_lsp

# Test de audio con mplayer o aplay (que funcionan con JACK)
echo "Testing audio output..."
# Generar tono de prueba de 3 segundos
ffmpeg -f lavfi -i "sine=frequency=440:duration=3" -ar 44100 /tmp/test_tone.wav 2>/dev/null
mplayer -ao jack /tmp/test_tone.wav 2>/dev/null || aplay -D jack /tmp/test_tone.wav

# Limpiar
kill $JACK_PID
rm /tmp/test_tone.wav