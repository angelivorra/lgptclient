# helpers.py

import subprocess

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
