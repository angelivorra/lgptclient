import os
import subprocess
import time

from flask import Flask, redirect, render_template
from helpers import check_service_status, get_devices, restart_service, save_config, read_config
from flask import request
from flask import jsonify
import socket
import pandas as pd


CSV_FILENAME = '/home/angel/midi_notes_log_server.csv'
CSV_ROBOT_FILENAME = '/home/angel/midi_notes_log.csv'
CSV_TIMIG_FILENAME = '/home/angel/timing_analysis.csv'

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
        app.logger.info('Main home')
        name = subprocess.run(['hostname'], capture_output=True, text=True).stdout.strip()        
        is_active, logs = check_service_status("servidor")
        devices = get_devices()
        config = read_config()
        with open('/home/angel/arecord.log', 'r') as file:
            audio = file.read()
        
        line_count = 0
        if os.path.exists(CSV_FILENAME):
            with open(CSV_FILENAME, 'r') as file:
                line_count = len(file.readlines()) - 1
                
        return render_template('home.html', name=name, is_active=is_active, logs=logs, devices = devices, config = config, audio = audio, line_count = line_count)

    @app.route('/resultados', methods=(['GET']))
    def resultados():
        name = subprocess.run(['hostname'], capture_output=True, text=True).stdout.strip()        

        return render_template('resultados.html', name=name)

    @app.route('/generadatos', methods=(['POST']))
    def genera_datos():
        def send_message_to_socket(message):            
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)            
            server_address = '/tmp/copilot.sock'
            try:
                sock.connect(server_address)
                sock.sendall(message.encode('utf-8'))
                # Wait briefly to ensure message is sent
                time.sleep(0.1)
            except Exception as e:
                return {"error": str(e)}
            finally:
                sock.close()
            return {"status": "ok"}
        
        app.logger.info('Send message')
        result = send_message_to_socket("generate-data")
        return jsonify(result)

    @app.route('/', methods=(['POST']))
    def restart():
        app.logger.info('Restart')
        delay = request.form.get('delay', type=int, default=0)
        debug = request.form.get('debug', type=bool, default=False)
        save_config({"delay": delay, "debug": debug})
        subprocess.run(['sudo', 'pkill', '-f', 'lgpt.rpi-exe'])        
        #restart_service("servidor")
        time.sleep(2)
        return jsonify({"status": "ok"})


    @app.route('/robot', methods=(['GET']))
    def robot():
        app.logger.info('robot')
        name = subprocess.run(['hostname'], capture_output=True, text=True).stdout.strip()        
        
        if os.path.exists(CSV_ROBOT_FILENAME):
            df = pd.read_csv(CSV_ROBOT_FILENAME)
            total_notes = len(df)
            differences = (df.iloc[:, 2] - df.iloc[:, 0]).abs()
            max_difference = differences.max()
            min_difference = differences.min()
            weighted_avg_difference = (differences * df.iloc[:, 1]).sum() / df.iloc[:, 1].sum()
            events_over_50ms = (differences > 100).sum()
        else:
            total_notes = 0
            max_difference = 0
            min_difference = 0
            weighted_avg_difference = 0
            events_over_50ms = 0
            
        if os.path.exists(CSV_TIMIG_FILENAME):
            df_timing = pd.read_csv(CSV_TIMIG_FILENAME)
            timing_differences = (df_timing.iloc[:, 2] - df_timing.iloc[:, 1]).abs()
            max_timing_difference = timing_differences.max()
            min_timing_difference = timing_differences.min()
            weighted_avg_timing_difference = (timing_differences * df_timing.iloc[:, 0]).sum() / df_timing.iloc[:, 0].sum()
            timing_events_over_50ms = (timing_differences > 10).sum()
        else:
            max_timing_difference = 0
            min_timing_difference = 0
            weighted_avg_timing_difference = 0
            timing_events_over_50ms = 0

        return render_template('robot.html', 
                               name=name, 
                               total_notes=total_notes, 
                               max_difference=max_difference, 
                               min_difference=min_difference, 
                               weighted_avg_difference=weighted_avg_difference, 
                               events_over_50ms=events_over_50ms,
                               max_timing_difference=max_timing_difference,
                               min_timing_difference=min_timing_difference,
                               weighted_avg_timing_difference=weighted_avg_timing_difference,
                               timing_events_over_50ms=timing_events_over_50ms)

    
    return app