import pyaudio

p = pyaudio.PyAudio()
for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    print(f"Device {i}: {info['name']} (Input Channels: {info['maxInputChannels']}, Output Channels: {info['maxOutputChannels']}, Default Sample Rate: {info['defaultSampleRate']})")
p.terminate()