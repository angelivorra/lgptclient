#!/bin/bash

# Create named pipe for audio streaming
mkfifo /tmp/audio_pipe

# Start recording to pipe in background
arecord -D hw:4,0 -f cd -t raw > /tmp/audio_pipe &

# Process through sox with delay to IQaudIODAC
sox -t raw -r 44100 -e signed-integer -b 16 -c 2 /tmp/audio_pipe -t alsa hw:1,0 delay 2

# Cleanup
rm /tmp/audio_pipe