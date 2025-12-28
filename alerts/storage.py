"""Persistent storage for alerts using JSON file."""
import json
import os
from typing import List, Dict
from pathlib import Path
from datetime import datetime


class AlertStorage:
    """Persistent storage for alerts using JSON file."""
    
    def __init__(self, storage_file: str = "alerts_history.json"):
        """
        Initialize alert storage.
        
        Args:
            storage_file: Path to JSON file for storing alerts
        """
        self.storage_file = storage_file
        self.storage_path = Path(storage_file)
        self._ensure_storage_dir()
    
    def _ensure_storage_dir(self):
        """Ensure the storage directory exists."""
        if self.storage_path.parent != Path("."):
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
    
    def load_alerts(self, max_alerts: int = 100) -> List[Dict]:
        """
        Load alerts from storage file.
        
        Args:
            max_alerts: Maximum number of alerts to return (most recent)
            
        Returns:
            List of alert dictionaries
        """
        if not self.storage_path.exists():
            return []
        
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                alerts = json.load(f)
                # Return most recent alerts, limited by max_alerts
                return alerts[:max_alerts] if isinstance(alerts, list) else []
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading alerts from storage: {e}")
            return []
    
    def save_alert(self, alert_data: Dict):
        """
        Save a single alert to storage.
        
        Args:
            alert_data: Alert dictionary to save
        """
        alerts = self.load_alerts(max_alerts=1000)  # Load more for appending
        alerts.insert(0, alert_data)  # Insert at beginning (most recent first)
        
        # Keep only the most recent alerts (e.g., last 1000)
        alerts = alerts[:1000]
        
        self._save_all(alerts)
    
    def save_all(self, alerts: List[Dict]):
        """
        Save all alerts to storage (replaces existing).
        
        Args:
            alerts: List of alert dictionaries
        """
        self._save_all(alerts)
    
    def _save_all(self, alerts: List[Dict]):
        """Internal method to save alerts to file."""
        try:
            # Write to temporary file first, then rename (atomic operation)
            temp_file = f"{self.storage_file}.tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(alerts, f, indent=2, ensure_ascii=False)
            
            # Atomic replace
            if os.path.exists(self.storage_file):
                os.replace(temp_file, self.storage_file)
            else:
                os.rename(temp_file, self.storage_file)
                
        except IOError as e:
            print(f"Error saving alerts to storage: {e}")
            # Clean up temp file if it exists
            temp_file = f"{self.storage_file}.tmp"
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
    
    def clear(self):
        """Clear all stored alerts."""
        if self.storage_path.exists():
            try:
                self.storage_path.unlink()
            except IOError as e:
                print(f"Error clearing alert storage: {e}")

