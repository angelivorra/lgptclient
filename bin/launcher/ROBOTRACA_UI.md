# Robotraca UI - Interfaz Gráfica de Texto

## Descripción

Nueva interfaz ncurses interactiva para gestionar el sistema de audio y LGPT del proyecto Robotraca.

## Características

1. **Título estilizado**: "ROBOTRACA" con diseño ASCII
2. **Monitoreo en tiempo real**:
   - Estado de JACK Server (con información de samplerate/bufsize)
   - Estado de ALSA Input
   - Estado de Delay Buffer
   - Estado de LGPT Tracker
   - Conexiones de audio activas

3. **Controles interactivos**:
   - **Reiniciar Sistema Audio**: Reinicia toda la pila de audio (jackd + alsa_in + delay_buffer)
   - **Iniciar LGPT**: Lanza LGPT Tracker (solo disponible si el audio está listo)
   - **Salir**: Cierra la aplicación
   
4. **Workflow**: Cuando cierras LGPT, vuelves automáticamente a la pantalla de Robotraca

## Archivos Modificados/Creados

- **`robotraca_ui.py`** (NUEVO): Interfaz ncurses completa
- **`run-lgpt.py`** (MODIFICADO): Ahora arranca la UI por defecto

## Uso

### Modo por defecto (con UI):
```bash
sudo systemctl restart lgpt.service
```

El servicio arrancará la interfaz Robotraca automáticamente.

### Modo legacy (sin UI, auto-loop):
```bash
LGPT_USE_UI=0 sudo systemctl restart lgpt.service
```

### Prueba manual:
```bash
# Detener el servicio
sudo systemctl stop lgpt.service

# Ejecutar manualmente
cd /home/angel/lgptclient/bin/launcher
sudo /home/angel/lgptclient/venv/bin/python run-lgpt.py
```

## Controles de la UI

- **↑/↓** o **j/k**: Navegar por el menú
- **ENTER**: Seleccionar opción
- **Q**: Salir rápido

## Estados de los Servicios

- 🟢 **Activo**: El servicio está corriendo correctamente
- 🟡 **Detenido**: El servicio no está activo
- 🔵 **Iniciando...**: El servicio se está iniciando
- 🔴 **Error**: Hay un problema con el servicio

## Colores

- **Cyan**: Títulos y encabezados
- **Verde**: Servicios activos
- **Amarillo**: Servicios detenidos
- **Rojo**: Errores
- **Azul/Cyan**: Botones y selección

## Notas Técnicas

- La UI actualiza el estado cada 500ms automáticamente
- Los logs completos se siguen escribiendo en `/home/angel/lgpt.log`
- El sistema de audio se mantiene corriendo en segundo plano
- LGPT se ejecuta en modo foreground y al cerrarse vuelves a la UI

## Troubleshooting

### La UI no arranca
```bash
# Verificar que curses esté disponible
python3 -c "import curses; print('OK')"

# Ver logs del servicio
sudo journalctl -u lgpt.service -f
```

### Terminal muy pequeña
La UI requiere un mínimo de 80x24 caracteres. Si la terminal es más pequeña, mostrará un mensaje de error.

### Volver al modo anterior
Si prefieres el modo anterior (auto-ejecutar LGPT sin UI), edita el archivo de servicio:
```bash
sudo nano /etc/systemd/system/lgpt.service
```

Y cambia la línea `ExecStart` para incluir la variable de entorno:
```
ExecStart=/bin/bash -c 'LGPT_USE_UI=0 /home/angel/lgptclient/venv/bin/python /home/angel/lgptclient/bin/launcher/run-lgpt.py'
```

Luego:
```bash
sudo systemctl daemon-reload
sudo systemctl restart lgpt.service
```
