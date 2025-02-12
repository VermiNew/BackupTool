"""Recovery and health monitoring module for the backup tool."""

import json
import logging
import os
import signal
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Callable
import psutil

class SystemHealthMonitor:
    """Monitors system health and resources."""
    
    def __init__(self, thresholds: Dict[str, float]):
        self.thresholds = {
            'cpu_percent': thresholds.get('cpu_percent', 90.0),
            'memory_percent': thresholds.get('memory_percent', 90.0),
            'disk_percent': thresholds.get('disk_percent', 90.0)
        }
        self.logger = logging.getLogger('backup_tool.health_monitor')
    
    def check_system_health(self) -> Dict[str, Any]:
        """Check current system health metrics."""
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        status = {
            'timestamp': datetime.now().isoformat(),
            'cpu_percent': cpu_percent,
            'memory_percent': memory.percent,
            'disk_percent': disk.percent,
            'is_healthy': True,
            'warnings': []
        }
        
        # Check thresholds
        if cpu_percent > self.thresholds['cpu_percent']:
            status['warnings'].append(f'High CPU usage: {cpu_percent}%')
            status['is_healthy'] = False
            
        if memory.percent > self.thresholds['memory_percent']:
            status['warnings'].append(f'High memory usage: {memory.percent}%')
            status['is_healthy'] = False
            
        if disk.percent > self.thresholds['disk_percent']:
            status['warnings'].append(f'High disk usage: {disk.percent}%')
            status['is_healthy'] = False
        
        return status

class CrashRecovery:
    """Handles crash recovery and backup state restoration."""
    
    def __init__(self, backup_dir: Path):
        self.backup_dir = backup_dir
        self.state_file = backup_dir / '.backup_state.json'
        self.pid_file = backup_dir / '.backup.pid'
        self.logger = logging.getLogger('backup_tool.crash_recovery')
        
    def save_state(self, state: Dict[str, Any]) -> None:
        """Save current backup state to file."""
        state['timestamp'] = datetime.now().isoformat()
        state['pid'] = os.getpid()
        
        with self.state_file.open('w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)
            
        # Update PID file
        with self.pid_file.open('w') as f:
            f.write(str(os.getpid()))
    
    def load_state(self) -> Optional[Dict[str, Any]]:
        """Load previous backup state if exists."""
        if not self.state_file.exists():
            return None
            
        try:
            with self.state_file.open('r', encoding='utf-8') as f:
                state = json.load(f)
                
            # Check if previous process is still running
            if self.pid_file.exists():
                with self.pid_file.open('r') as f:
                    pid = int(f.read().strip())
                    if psutil.pid_exists(pid):
                        self.logger.warning(f'Previous backup process (PID: {pid}) is still running')
                        return None
            
            return state
        except (json.JSONDecodeError, ValueError) as e:
            self.logger.error(f'Failed to load backup state: {e}')
            return None
    
    def cleanup_state(self) -> None:
        """Clean up state files."""
        if self.state_file.exists():
            self.state_file.unlink()
        if self.pid_file.exists():
            self.pid_file.unlink()

class AutomaticRecovery:
    """Implements automatic recovery mechanisms."""
    
    def __init__(self, backup_dir: Path, health_check_interval: int = 60):
        self.backup_dir = backup_dir
        self.health_check_interval = health_check_interval
        self.health_monitor = SystemHealthMonitor({})
        self.crash_recovery = CrashRecovery(backup_dir)
        self.logger = logging.getLogger('backup_tool.auto_recovery')
        self._stop_event = threading.Event()
        self._monitor_thread = None
        
    def start_monitoring(self, on_health_warning: Callable[[str], None]) -> None:
        """Start health monitoring in a separate thread."""
        def monitor_health():
            while not self._stop_event.is_set():
                try:
                    health_status = self.health_monitor.check_system_health()
                    if not health_status['is_healthy']:
                        for warning in health_status['warnings']:
                            on_health_warning(warning)
                except Exception as e:
                    self.logger.error(f'Health check failed: {e}')
                finally:
                    self._stop_event.wait(self.health_check_interval)
        
        self._monitor_thread = threading.Thread(target=monitor_health, daemon=True)
        self._monitor_thread.start()
    
    def stop_monitoring(self) -> None:
        """Stop health monitoring."""
        if self._monitor_thread:
            self._stop_event.set()
            self._monitor_thread.join()
    
    def setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            self.logger.info(f'Received signal {signum}, performing cleanup...')
            self.stop_monitoring()
            self.crash_recovery.cleanup_state()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler) 