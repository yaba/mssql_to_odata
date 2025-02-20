import json
import os

CONFIG_FILE = 'config/db_config.json'

def ensure_config_dir():
    os.makedirs('config', exist_ok=True)

def save_config(config):
    ensure_config_dir()
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def load_config():
    ensure_config_dir()
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {
        'server': 'localhost',
        'database': '',
        'username': '',
        'password': '',
        'driver': 'ODBC Driver 18 for SQL Server'
    }

