import logging
import platform
import os
import json
from typing import Dict, Any

def setup_logging(log_file: str = "battery_manager.log") -> None:
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def get_platform_info() -> Dict[str, Any]:
    return {
        'system': platform.system(),
        'release': platform.release(),
        'version': platform.version(),
        'machine': platform.machine(),
        'processor': platform.processor()
    }

def save_config(config: Dict[str, Any], filename: str = "config.json") -> None:
    with open(filename, 'w') as f:
        json.dump(config, f, indent=4)

def load_config(filename: str = "config.json") -> Dict[str, Any]:
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            return json.load(f)
    return {}

