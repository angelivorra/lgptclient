# File: /midi-controller/midi-controller/src/config/settings.py

import json
import os

class Settings:
    def __init__(self, config_file='/home/angel/config.json'):
        self.config_file = config_file
        self.instruments = {}
        self.tiempo = 0
        self.load_config()

    def load_config(self):
        if os.path.exists(self.config_file):
            with open(self.config_file) as f:
                config = json.load(f)
                self.instruments = config.get("instruments", {})
                self.tiempo = config.get("tiempo", 0)
        else:
            raise FileNotFoundError(f"Configuration file not found: {self.config_file}")

    def get_instruments(self):
        return self.instruments

    def get_tiempo(self):
        return self.tiempo