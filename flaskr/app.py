import os
import subprocess
import time

from flask import Flask, redirect, render_template
from helpers import check_service_status, get_devices, restart_service, save_config, read_config
from flask import request
from flask import jsonify


def create_app():
    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass



    @app.route('/', methods=(['GET']))
    def home():
        name = subprocess.run(['hostname'], capture_output=True, text=True).stdout.strip()        
        is_active, logs = check_service_status("servidor")
        devices = get_devices()
        config = read_config()
        with open('/home/angel/arecord.log', 'r') as file:
            audio = file.read()
        #print(config)
        return render_template('home.html', name=name, is_active=is_active, logs=logs, devices = devices, config = config, audio = audio)

    @app.route('/', methods=(['POST']))
    def restart():        
        delay = request.form.get('delay', type=int, default=0)
        debug = request.form.get('debug', type=bool, default=False)
        save_config({"delay": delay, "debug": debug})
        subprocess.run(['sudo', 'pkill', '-f', 'lgpt.rpi-exe'])        
        restart_service("servidor")
        time.sleep(2)
        return jsonify({"status": "ok"})


    @app.route('/robot', methods=(['GET']))
    def robot():
        name = subprocess.run(['hostname'], capture_output=True, text=True).stdout.strip()        
        is_active, logs = check_service_status("cliente")
        
        return render_template('robot.html', name=name, is_active=is_active, logs=logs)

    
    return app