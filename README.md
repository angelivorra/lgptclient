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