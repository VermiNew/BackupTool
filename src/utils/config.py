import json
from pathlib import Path
from typing import Dict

DEFAULT_CONFIG = {
    'interface': {
        'dark_mode': True,
        'window_size': {
            'width': 800,
            'height': 600
        },
        'theme': {
            'dark': {
                'background': '#2c2c2c',
                'text': '#ffffff',
                'primary': '#3498db',
                'secondary': '#2ecc71',
                'warning': '#f1c40f',
                'error': '#e74c3c'
            }
        }
    },
    'backup': {
        'chunk_size': 1024 * 1024,  # 1MB default
        'verify_after_copy': True,
        'auto_continue_on_error': False,
        'exclude_patterns': [
            '*.tmp',
            '~*',
            'Thumbs.db',
            '.DS_Store'
        ]
    },
    'logging': {
        'directory': 'logs',
        'max_size': 10 * 1024 * 1024,  # 10MB
        'backup_count': 5,
        'level': 'INFO'
    }
}

def load_config() -> Dict:
    """Load configuration from file or create default."""
    config_path = Path('config.json')
    
    try:
        if config_path.exists():
            with config_path.open('r') as f:
                user_config = json.load(f)
                # Merge with defaults
                return {**DEFAULT_CONFIG, **user_config}
        else:
            # Save default config
            with config_path.open('w') as f:
                json.dump(DEFAULT_CONFIG, f, indent=4)
            return DEFAULT_CONFIG
            
    except Exception as e:
        print(f"Error loading config: {e}")
        return DEFAULT_CONFIG 