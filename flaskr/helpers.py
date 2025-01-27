# helpers.py

import subprocess
import socket

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


def get_extra_device_data(row):
    #Call the 


def getDevices():
    for row in IPS:
        row.update(get_extra_device_data(row))