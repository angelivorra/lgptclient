import csv
import os
import subprocess
import time

from flask import Flask, redirect, render_template
from helpers import check_service_status, get_devices, restart_service, save_config, read_config, save_config_value
from flask import request
from flask import jsonify
import socket
import pandas as pd
import shutil


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
        lgpt_is_active, lgpt_logs = check_service_status("lgpt")
        devices = get_devices()
        config = read_config()
        with open('/home/angel/arecord.log', 'r') as file:
            audio = file.read()
        
        line_count = 0
        if os.path.exists(CSV_FILENAME):
            with open(CSV_FILENAME, 'r') as file:
                line_count = len(file.readlines()) - 1
                
        return render_template('home.html', 
                               name=name, 
                               is_active=is_active, 
                               logs=logs, 
                               devices = devices, 
                               config = config, 
                               audio = audio, 
                               line_count = line_count,
                               lgpt_is_active = lgpt_is_active, 
                               lgpt_logs = lgpt_logs
                               )

    @app.route('/proceso', methods=(['GET']))
    def proceso():
        line_count = 0
        if os.path.exists(CSV_FILENAME):
            with open(CSV_FILENAME, 'r') as file:
                line_count = len(file.readlines()) - 1
        return jsonify({"data": line_count})


    @app.route('/resultados', methods=(['GET']))
    def resultados():
        name = subprocess.run(['hostname'], capture_output=True, text=True).stdout.strip()        

        return render_template('resultados.html', name=name)

    
    @app.route('/testvelocidad/<int:intvalue>', methods=(['GET']))
    def test_velocidad(intvalue):
        app.logger.info('Test Velocidad')
        name = subprocess.run(['hostname'], capture_output=True, text=True).stdout.strip()
        
        file_count = 0
        if os.path.exists(CSV_FILENAME):
            with open(CSV_FILENAME, 'r') as file:
                file_count = len(file.readlines()) - 1
        
        return render_template('test.html', name=name, intvalue=intvalue * 3, file_count=file_count)
    
    @app.route('/ruido', methods=(['POST']))
    def ruido():
        ruido = request.form.get('ruido', type=str, default='false')
        print(f"Ruido({ruido})")
        ruido = ruido.lower() == 'true'
        save_config_value("ruido", ruido)
        return jsonify({})
    
    
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
        data = request.form.get('data', type=int, default=50)
        result = send_message_to_socket("generate-data," + str(data))
        return jsonify(result)

    @app.route('/', methods=(['POST']))
    def restart():
        app.logger.info('Restart')
        delay = request.form.get('delay', type=int, default=0)
        debug = request.form.get('debug', type=bool, default=False)
        save_config_value("delay", delay)
        save_config_value("debug", debug)
        #subprocess.run(['sudo', 'pkill', '-f', 'lgpt.rpi-exe'])        
        restart_service("lgpt")
        time.sleep(2)
        return jsonify({"status": "ok"})

    @app.route('/limpia', methods=(['POST']))
    def limpia():
        app.logger.info('Limpia')
        with open(CSV_TIMIG_FILENAME, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['expected_timestamp', 'executed_timestamp'])
        with open(CSV_ROBOT_FILENAME, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["timestamp_sent", "note", "timestamp_received"])
        
        return jsonify({"status": "ok"})


    @app.route('/robot', methods=(['GET']))
    def robot():
        app.logger.info('robot')
        name = subprocess.run(['hostname'], capture_output=True, text=True).stdout.strip()        

        stats = shutil.disk_usage("/")
        used_gb = stats.used / 1024**3
        total_gb = stats.total / 1024**3
        disk_usage = f"{used_gb:.2f} GB used of {total_gb:.2f} GB total"
        
        #Estadisticas
        
        total_registros = 0
        tnum_registros = 0
        num_registros = 0
        media_diff = 0
        max_diff = 0
        min_diff = 0
        tmedia_diff = 0
        tmax_diff = 0
        tmin_diff = 0
        
        if os.path.exists(CSV_TIMIG_FILENAME):
            df = pd.read_csv(CSV_TIMIG_FILENAME)
            df = df[(df['expected_timestamp'] != 0) & (df['executed_timestamp'] != 0)]
            df['diff'] = abs(df['expected_timestamp'] - df['executed_timestamp'])
            tnum_registros = len(df)
            if tnum_registros:
                tmedia_diff = df['diff'].mean()
                tmax_diff = df['diff'].max()
                tmin_diff = df['diff'].min()
                total_registros = tnum_registros
            
        if os.path.exists(CSV_ROBOT_FILENAME):
            df = pd.read_csv(CSV_ROBOT_FILENAME)
            df = df[(df['timestamp_sent'] != 0) & (df['timestamp_received'] != 0)]
            df['diff'] = abs(df['timestamp_sent'] - df['timestamp_received'])
            num_registros = len(df)
            if num_registros:
                media_diff = df['diff'].mean()
                max_diff = df['diff'].max()
                min_diff = df['diff'].min()
                total_registros += num_registros
        
            
        return render_template('robot.html', name=name, disk_usage=disk_usage, datos = {
            "total_registros": total_registros,
            "num_registros": num_registros,
            "media_diff": media_diff,
            "max_diff": max_diff,
            "min_diff": min_diff,
            "tnum_registros": tnum_registros,
            "tmedia_diff": tmedia_diff,
            "tmax_diff": tmax_diff,
            "tmin_diff": tmin_diff
        })

    
    return app