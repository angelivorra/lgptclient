#!/usr/bin/python3
from subprocess import run

if __name__ == '__main__':
    print('Instalamos servidor...')
    run(["sudo","apt","update"])
    run(["sudo","apt","upgrade","-y"])
    run(["git","pull","origin", "main"], cwd=r'/home/angel/lgptclient')
    #run(["rm","-r","/home/angel/lgptclient/venv"])
    #run(["python3", "-m", "venv", "/home/angel/lgptclient/venv"])
    
