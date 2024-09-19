import os
import subprocess
import platform
from datetime import datetime

def get_wifi_info():

        # Linux: use `iwconfig` for network information
        result = subprocess.run(['iwconfig'], capture_output=True, text=True).stdout
        wifi_info = {
            'name': None,
            'signal_strength': None,
            'link_speed': None
        }
        
        for line in result.splitlines():
            if 'ESSID' in line:
                wifi_info['name'] = line.split('"')[1]
            elif 'Signal level' in line:
                wifi_info['signal_strength'] = line.split('=')[-1].strip()
            elif 'Bit Rate' in line:
                wifi_info['link_speed'] = line.split('=')[1].split(' ')[0] + ' Mbps'

        return wifi_info
   


def generate_html_report(wifi_info):
    report_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta http-equiv="X-UA-Compatible" content="IE=edge">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>WiFi Quality Report</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 40px;
                background-color: #f5f5f5;
            }}
            h1 {{
                text-align: center;
                color: #333;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 20px;
            }}
            th, td {{
                padding: 12px;
                border: 1px solid #ddd;
                text-align: left;
            }}
            th {{
                background-color: #4CAF50;
                color: white;
            }}
        </style>
    </head>
    <body>
        <h1>WiFi Quality Report</h1>
        <p>Report generated at: {report_time}</p>
        <table>
            <tr>
                <th>WiFi Network Name (SSID)</th>
                <td>{wifi_info.get('name', 'N/A')}</td>
            </tr>
            <tr>
                <th>Signal Strength</th>
                <td>{wifi_info.get('signal_strength', 'N/A')}</td>
            </tr>
            <tr>
                <th>Link Speed</th>
                <td>{wifi_info.get('link_speed', 'N/A')}</td>
            </tr>
            <tr>
                <th>Status</th>
                <td>{'Connected' if wifi_info.get('name') else 'Not Connected'}</td>
            </tr>
        </table>
    </body>
    </html>
    """
    return html_content

def save_report(html_content, filename="wifi_report.html"):
    with open(filename, 'w') as file:
        file.write(html_content)
    print(f"Report saved as {filename}")

if __name__ == "__main__":
    wifi_info = get_wifi_info()
    html_report = generate_html_report(wifi_info)
    save_report(html_report)