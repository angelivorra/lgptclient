#!/bin/sh
# Hay que activar el STP en sudo raspi-config
# Hqy que editar el archivo sudo nano /boot/firmware/config.txt y descomentar dtparam=i2c_arm=on
# y comentar
# Enable DRM VC4 V3D driver
#dtoverlay=vc4-kms-v3d
#max_framebuffers=2


sudo apt update
sudo apt upgrade -y
sudo apt install -y python3-setuptools mc unzip python3-pip python3-pil python3-numpy cmake  libraspberrypi-dev raspberrypi-kernel-headers

cd
wget http://www.airspayce.com/mikem/bcm2835/bcm2835-1.71.tar.gz
tar zxvf bcm2835-1.71.tar.gz 
cd bcm2835-1.71/
sudo ./configure && sudo make && sudo make check && sudo make install

cd
wget https://project-downloads.drogon.net/wiringpi-latest.deb
sudo dpkg -i wiringpi-latest.deb

cd
wget https://github.com/joan2937/lg/archive/master.zip
unzip master.zip
cd lg-master
sudo make install

cd
wget https://files.waveshare.com/upload/8/8d/LCD_Module_RPI_code.zip
unzip LCD_Module_RPI_code.zip
cd LCD_Module_RPI_code/RaspberryPi/
cd c
sudo make -j 8

cd
wget https://files.waveshare.com/upload/1/18/Waveshare_fbcp.zip
unzip Waveshare_fbcp.zip
cd Waveshare_fbcp/
sudo chmod +x ./shell/*

sudo reboot