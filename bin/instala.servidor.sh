#!/bin/sh
sudo apt update
sudo apt upgrade -y

# Poner esto en /etc/rc.local
# nmcli dev wifi hotspot ifname wlan0 ssid test password "test1234"

sudo apt-install git libsdl1.2-dev -y

git config --global user.name "Angel Ivorra"
git config --global user.email "angel.ivorra@gmail.com"

