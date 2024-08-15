# Servidor robot

## Poner esto en /etc/rc.local
```
nmcli dev wifi hotspot ifname wlan0 ssid test password "test1234"
```

## Instalar repositorio git
```
git clone git@gitlab.com:angel.ivorra/lgptclient.git /home/angel/lgptclient
```

## Instalar servidor
```shell
/home/angel/lgptclient/bin/instala.servidor.sh
```

## Dependencias python
```shell
 python3 -m venv /home/angel/lgptclient/venv
 source /home/angel/lgptclient/venv/bin/activate
```

## Instalamos servidor /etc/system.d/system/servidor.service
```ini
[Unit]
Description=Puto robot servidor
After=syslog.target network.target alsa-utils.target

[Service]
ExecStart=/home/angel/lgptclient/venv/bin/python3 /home/angel/lgptclient/bin/server-tcp.py 

Restart=always
RestartSec=120

[Install]
WantedBy=multi-user.target
```

## Poner esto en /etc/rc.local
```
nmcli dev wifi hotspot ifname wlan0 ssid test password "test1234"
sudo /home/angel/lgptclient/venv/bin/python3 /home/angel/lgptclient/bin/lgpt.py & 
```

# Inslacion cliente

## Actiamos spi 
```
sudo raspi-config
```

## Tocamos rc.local
```
descomentar dtparam=i2c_arm=on
# y comentar
# Enable DRM VC4 V3D driver
#dtoverlay=vc4-kms-v3d
#max_framebuffers=2
```

## Instalamos 
```
asd
```

## Tocamos rc.local
```
hdmi_force_hotplug=1
hdmi_cvt=hdmi_cvt 560 480 60 6 0 0 0
hdmi_group=2
hdmi_mode=1
hdmi_mode=87
display_rotate=3
```

## Comando para arrancar servicio cliente
```
sudo /home/angel/lgptclient/venv/bin/python3 /home/angel/lgptclient/bin/cliente-bluetooth.py 
```

## Comando para arrancar servidor
```
sudo /home/angel/lgptclient/venv/bin/python3 /home/angel/lgptclient/bin/server-movida.py 
```

## Comando para ver clientes conectados
```
arp -a
```

