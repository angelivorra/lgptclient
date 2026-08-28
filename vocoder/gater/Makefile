# Plugin LADSPA lgpt_gater (gate rítmico sincronizado a BPM).
#
# Se compila en la propia máquina de destino (este PC y la Raspberry Pi del
# vocoder, ARM): así el .so tiene siempre la arquitectura correcta sin depender
# de un toolchain cruzado ni de internet en la Pi. `ladspa.h` va vendorado en
# este directorio para no depender del paquete ladspa-sdk.
#
#   make            -> lgpt_gater.so
#   sudo make install  -> /usr/lib/ladspa/lgpt_gater.so  (ruta del <Binary> del carxp)
#   make clean

CC        ?= cc
CFLAGS    ?= -O2 -fPIC -Wall
PREFIX    ?= /usr
LADSPA_DIR ?= $(PREFIX)/lib/ladspa

TARGET = lgpt_gater.so

$(TARGET): lgpt_gater.c ladspa.h
	$(CC) $(CFLAGS) -I. -shared -o $@ lgpt_gater.c -lm

install: $(TARGET)
	install -d $(DESTDIR)$(LADSPA_DIR)
	install -m 644 $(TARGET) $(DESTDIR)$(LADSPA_DIR)/$(TARGET)

clean:
	rm -f $(TARGET)

.PHONY: install clean
