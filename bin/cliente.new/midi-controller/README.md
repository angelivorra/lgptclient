# README.md

# MIDI Controller

This project is a MIDI controller application designed to manage and control MIDI instruments and display images on an HDMI display. It utilizes GPIO pins for instrument activation and handles TCP connections for receiving MIDI events.

## Project Structure

```
midi-controller
├── src
│   ├── config
│   │   ├── __init__.py
│   │   └── settings.py
│   ├── controllers
│   │   ├── __init__.py
│   │   ├── display_controller.py
│   │   └── gpio_controller.py
│   ├── services
│   │   ├── __init__.py
│   │   ├── framebuffer_service.py
│   │   └── tcp_service.py
│   ├── utils
│   │   ├── __init__.py
│   │   └── logger.py
│   ├── __init__.py
│   └── main.py
├── configs
│   └── config.json
├── data
│   └── images
├── tests
│   └── __init__.py
├── requirements.txt
└── README.md
```

## Installation

1. Clone the repository:
   ```
   git clone <repository-url>
   cd midi-controller
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

## Configuration

The configuration settings are stored in `configs/config.json`. This file includes instrument mappings and timing settings. Modify this file to customize the behavior of the MIDI controller.

## Usage

To run the application, execute the following command:
```
python src/main.py
```

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any improvements or bug fixes.

## License

This project is licensed under the MIT License. See the LICENSE file for more details.