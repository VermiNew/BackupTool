import json
from pathlib import Path
from typing import Dict, Tuple

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

def deep_merge(default: Dict, user: Dict) -> Dict:
    """Deep merge two dictionaries.
    
    Args:
        default: Default dictionary
        user: User dictionary to merge
        
    Returns:
        Merged dictionary
    """
    result = default.copy()
    for key, value in user.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result

def load_config() -> Tuple[Dict, str]:
    """Load configuration from file or create default.
    
    Returns:
        Tuple containing:
            - config: Dictionary with configuration
            - config_path: Path to the configuration file
    """
    config_path = Path('config.json')
    
    try:
        if config_path.exists():
            with config_path.open('r') as f:
                user_config = json.load(f)
                # Deep merge with defaults
                return deep_merge(DEFAULT_CONFIG, user_config), str(config_path.absolute())
        else:
            # Save default config
            with config_path.open('w') as f:
                json.dump(DEFAULT_CONFIG, f, indent=4)
            return DEFAULT_CONFIG, str(config_path.absolute())
            
    except Exception as e:
        print(f"Error loading config: {e}")
        return DEFAULT_CONFIG, str(config_path.absolute()) 