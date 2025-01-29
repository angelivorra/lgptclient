# helpers.py

import subprocess
import socket
import json

IPS = [
    {'ip': '192.168.0.3', 'name': 'Obdulia'},
    {'ip': '192.168.0.4', 'name': 'Carmen'},
]


def check_service_status(service_name):
    try:
        # Check if the service is active
        status_cmd = f'systemctl is-active {service_name}'
        status_result = subprocess.run(status_cmd.split(), capture_output=True, text=True)
        service_active = status_result.stdout.strip() == 'active'
        
        # Get the last lines of the service's log
        log_cmd = f'sudo journalctl -u {service_name} -n 10 --no-pager'
        log_result = subprocess.run(log_cmd.split(), capture_output=True, text=True)
        log_output = log_result.stdout.strip()

        return service_active, log_output

    except Exception as e:
        return False, str(e)
    
    
def send_command_locally(cmd_data, socket_path='/tmp/copilot.sock'):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(socket_path)
            s.sendall(cmd_data.encode())
            response = s.recv(1024)
        return response.decode()
    except Exception as e:
        return str(e)

def read_config(file_path='/home/angel/lgptclient/bin/config.json'):
    try:
        with open(file_path, 'r') as config_file:
            config = json.load(config_file)
        return config
    except Exception as e:
        return {"error": str(e)}

def load_config():
    config = read_config()
    if "error" in config:
        print(f"Error reading config: {config['error']}")
        return None
    return config

def save_config(config, file_path='/home/angel/lgptclient/bin/config.json'):
    try:
        with open(file_path, 'w') as config_file:
            json.dump(config, config_file, indent=4)
        return True
    except Exception as e:
        return {"error": str(e)}
    
def restart_service(service_name):
    try:
        # Restart the service
        restart_cmd = f'sudo systemctl restart {service_name}'
        restart_result = subprocess.run(restart_cmd.split(), capture_output=True, text=True)
        
        if restart_result.returncode == 0:
            return True, "Service restarted successfully"
        else:
            return False, restart_result.stderr.strip()
    except Exception as e:
        return False, str(e)

def get_extra_device_data(row):
    return {}


def get_devices():
    r = IPS.copy()
    for row in r:
        extra_data = get_extra_device_data(row)
        row.update(extra_data)
        return r