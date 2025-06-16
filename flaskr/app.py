import csv
import os
import subprocess
import time

from flask import Flask, redirect, render_template, current_app # Added current_app
from helpers import check_service_status, get_devices, restart_service, save_config, read_config, save_config_value
from flask import request
from flask import jsonify
import socket
import pandas as pd
import shutil


CSV_FILENAME = '/home/angel/midi_notes_log_server.csv'
CSV_ROBOT_FILENAME = '/home/angel/midi_notes_log.csv'
CSV_TIMIG_FILENAME = '/home/angel/timing_analysis.csv'

def get_robot_stats():
    logger = current_app.logger
    logger.info("Executing get_robot_stats")
    stats = shutil.disk_usage("/")
    used_gb = stats.used / 1024**3
    total_gb = stats.total / 1024**3
    disk_usage = f"{used_gb:.2f} GB used of {total_gb:.2f} GB total"
    current_time = time.strftime('%Y-%m-%d %H:%M:%S')
    
    num_registros = 0
    media_diff = 0.0
    max_diff = 0.0
    min_diff = 0.0
    signals_ok_pantalla = 0
    
    tnum_registros = 0
    tmedia_diff = 0.0
    tmax_diff = 0.0
    tmin_diff = 0.0
    signals_ok_bateria = 0

    # Process Timing Analysis CSV (Bateria)
    if os.path.exists(CSV_TIMIG_FILENAME):
        try:
            df_timing = pd.read_csv(CSV_TIMIG_FILENAME)
            if not df_timing.empty and 'expected_timestamp' in df_timing.columns and 'executed_timestamp' in df_timing.columns:
                df_timing = df_timing[
                    (df_timing['expected_timestamp'] != 0) & 
                    (df_timing['executed_timestamp'] != 0)
                ].copy()
                if not df_timing.empty:
                    df_timing.loc[:, 'diff'] = abs(df_timing['expected_timestamp'] - df_timing['executed_timestamp'])
                    tnum_registros = len(df_timing)
                    if tnum_registros > 0:
                        tmedia_diff = df_timing['diff'].mean()
                        tmax_diff = df_timing['diff'].max()
                        tmin_diff = df_timing['diff'].min()
                        signals_ok_bateria = len(df_timing[df_timing['diff'] <= 25]) # Signals within 25ms
            else:
                logger.info(f"'{CSV_TIMIG_FILENAME}' is empty or missing required columns.")
        except pd.errors.EmptyDataError:
            logger.info(f"File '{CSV_TIMIG_FILENAME}' is empty.")
        except Exception as e:
            logger.error(f"Error processing '{CSV_TIMIG_FILENAME}': {str(e)}")

    # Process Robot Log CSV (Pantalla)
    if os.path.exists(CSV_ROBOT_FILENAME):
        try:
            df_robot = pd.read_csv(CSV_ROBOT_FILENAME)
            if not df_robot.empty and 'timestamp_sent' in df_robot.columns and 'timestamp_received' in df_robot.columns:
                df_robot = df_robot[
                    (df_robot['timestamp_sent'] != 0) & 
                    (df_robot['timestamp_received'] != 0)
                ].copy()
                if not df_robot.empty:
                    df_robot.loc[:, 'diff'] = abs(df_robot['timestamp_sent'] - df_robot['timestamp_received'])
                    num_registros = len(df_robot)
                    if num_registros > 0:
                        media_diff = df_robot['diff'].mean()
                        max_diff = df_robot['diff'].max()
                        min_diff = df_robot['diff'].min()
                        signals_ok_pantalla = len(df_robot[df_robot['diff'] <= 25]) # Signals within 25ms
            else:
                logger.info(f"'{CSV_ROBOT_FILENAME}' is empty or missing required columns.")
        except pd.errors.EmptyDataError:
            logger.info(f"File '{CSV_ROBOT_FILENAME}' is empty.")
        except Exception as e:
            logger.error(f"Error processing '{CSV_ROBOT_FILENAME}': {str(e)}")
            
    total_registros_procesados = tnum_registros + num_registros
    total_signals_ok = signals_ok_pantalla + signals_ok_bateria

    # Prepare data for JSON, ensuring native Python types
    data_to_return = {
        "disk_usage": disk_usage,
        "current_time": current_time,
        "total_registros_procesados": int(total_registros_procesados),
        "total_signals_ok": int(total_signals_ok),
        
        "num_registros_pantalla": int(num_registros),
        "media_diff_pantalla": float(media_diff) if pd.notna(media_diff) else 0.0,
        "max_diff_pantalla": float(max_diff) if pd.notna(max_diff) else 0.0,
        "min_diff_pantalla": float(min_diff) if pd.notna(min_diff) else 0.0,
        "signals_ok_pantalla": int(signals_ok_pantalla),
        
        "num_registros_bateria": int(tnum_registros),
        "media_diff_bateria": float(tmedia_diff) if pd.notna(tmedia_diff) else 0.0,
        "max_diff_bateria": float(tmax_diff) if pd.notna(tmax_diff) else 0.0,
        "min_diff_bateria": float(tmin_diff) if pd.notna(tmin_diff) else 0.0,
        "signals_ok_bateria": int(signals_ok_bateria),
    }
    logger.info(f"Data from get_robot_stats: {data_to_return}")
    for key, value in data_to_return.items():
        logger.info(f"Key: {key}, Value: {value}, Type: {type(value)}")

    return data_to_return

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
        current_time = time.strftime('%Y-%m-%d %H:%M:%S')
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
                               lgpt_logs = lgpt_logs,
                               current_time=current_time
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
        robot_data = get_robot_stats()
        return render_template('robot.html', name=name, datos=robot_data)

    @app.route('/robot_data', methods=(['GET']))
    def robot_data_endpoint():
        current_app.logger.info('Request received for /robot_data') # Use current_app.logger here too for consistency
        try:
            data = get_robot_stats()
            current_app.logger.info(f"Data to jsonify in /robot_data: {data}")
            return jsonify(data)
        except Exception as e:
            current_app.logger.error(f"Error in /robot_data endpoint: {str(e)}", exc_info=True)
            return jsonify({"error": "Internal server error", "message": str(e)}), 500
    
    return app