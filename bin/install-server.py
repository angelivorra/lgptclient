#!/usr/bin/python3
from subprocess import run

if __name__ == '__main__':
    print('Instalamos servidor...')
    run(["sudo","apt","update"])
    run(["sudo","apt","upgrade","-y"])
    run(["git","pull","origin", "main"], cwd=r'/home/angel/lgptclient')
    run(["rm","-r","/home/angel/lgptclient/venv"])
    run(["python3", "-m", "venv", "/home/angel/lgptclient/venv"])
    run(["/home/angel/lgptclient/venv/bin/python", "-m", "pip", "install", "--upgrade", "pip"])
    run(["/home/angel/lgptclient/venv/bin/pip3", "install", "-r", "/home/angel/lgptclient/requirements.txt"])
    run(["/home/angel/lgptclient/venv/bin/ansible-playbook", "/home/angel/lgptclient/ansible/init-server.yaml"])
    
