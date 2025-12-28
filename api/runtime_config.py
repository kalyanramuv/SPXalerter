"""Runtime configuration for the application."""
from typing import Optional, List, Dict
from datetime import datetime
import json
import os
from pathlib import Path


class RuntimeConfig:
    """Runtime configuration that can be changed via API."""
    
    def __init__(self, default_polling_interval: int = 30, config_file: str = "runtime_config.json"):
        self.config_file = config_file
        self.config_path = Path(config_file)
        
        # Load persisted settings
        persisted_config = self._load_config()
        
        self.bypass_market_hours: bool = persisted_config.get("bypass_market_hours", False)
        self.use_mock_data: bool = persisted_config.get("use_mock_data", False)
        # Use persisted value, or default, or provided default
        self.polling_interval_seconds: Optional[int] = persisted_config.get("polling_interval_seconds", default_polling_interval)
        self.historical_bars_count: int = persisted_config.get("historical_bars_count", 2000)
        # RSI chart display settings
        self.rsi_ma_type: Optional[str] = persisted_config.get("rsi_ma_type", "None")
        self.rsi_ma_length: Optional[int] = persisted_config.get("rsi_ma_length", 14)
        self.show_rsi_ma: bool = persisted_config.get("show_rsi_ma", False)
        self.show_divergence: bool = persisted_config.get("show_divergence", False)
        
        self.rsi_history_1min: List[Dict] = []
        self.rsi_history_5min: List[Dict] = []
        self.rsi_history_30min: List[Dict] = []
        self.max_rsi_history = 2000
    
    def _load_config(self) -> Dict:
        """Load persisted configuration from file."""
        if not self.config_path.exists():
            return {}
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading runtime config: {e}")
            return {}
    
    def _save_config(self):
        """Save configuration to file."""
        try:
            config = {
                "bypass_market_hours": self.bypass_market_hours,
                "use_mock_data": self.use_mock_data,
                "polling_interval_seconds": self.polling_interval_seconds,
                "historical_bars_count": self.historical_bars_count,
                "rsi_ma_type": self.rsi_ma_type,
                "rsi_ma_length": self.rsi_ma_length,
                "show_rsi_ma": self.show_rsi_ma,
                "show_divergence": self.show_divergence
            }
            
            # Write to temporary file first, then rename (atomic operation)
            temp_file = f"{self.config_file}.tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            # Atomic replace
            if os.path.exists(self.config_file):
                os.replace(temp_file, self.config_file)
            else:
                os.rename(temp_file, self.config_file)
        except IOError as e:
            print(f"Error saving runtime config: {e}")
            # Clean up temp file if it exists
            temp_file = f"{self.config_file}.tmp"
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
    
    def set_bypass_market_hours(self, value: bool):
        """Set bypass market hours flag."""
        self.bypass_market_hours = value
        self._save_config()
    
    def set_use_mock_data(self, value: bool):
        """Set use mock data flag."""
        self.use_mock_data = value
        self._save_config()
    
    def set_polling_interval(self, value: int):
        """Set polling interval in seconds."""
        if value < 1:
            raise ValueError("Polling interval must be at least 1 second")
        self.polling_interval_seconds = value
        self._save_config()
    
    def set_historical_bars_count(self, value: int):
        """Set historical bars count."""
        if value < 1:
            raise ValueError("Historical bars count must be at least 1")
        self.historical_bars_count = value
        self._save_config()
    
    def get_polling_interval(self, default: int) -> int:
        """Get polling interval, using default if not set."""
        return self.polling_interval_seconds if self.polling_interval_seconds is not None else default
    
    def clear_rsi_history(self, timeframe: str):
        """Clear RSI history for a timeframe."""
        setattr(self, f'rsi_history_{timeframe}', [])
    
    def add_rsi_point(self, timeframe: str, timestamp: datetime, rsi_value: float, index: int):
        """Add RSI data point for a timeframe."""
        history = getattr(self, f'rsi_history_{timeframe}', [])
        point = {
            "timestamp": timestamp.isoformat(),
            "rsi": rsi_value,
            "index": index
        }
        # Check if we already have this index (for updating)
        existing_idx = next((i for i, p in enumerate(history) if p["index"] == index), None)
        if existing_idx is not None:
            history[existing_idx] = point
        else:
            history.append(point)
        # Sort by index and keep only last max_rsi_history points
        history.sort(key=lambda x: x["index"])
        if len(history) > self.max_rsi_history:
            history = history[-self.max_rsi_history:]
        setattr(self, f'rsi_history_{timeframe}', history)
    
    def set_rsi_ma_type(self, value: str):
        """Set RSI MA type."""
        self.rsi_ma_type = value
        self._save_config()
    
    def set_rsi_ma_length(self, value: int):
        """Set RSI MA length."""
        if value < 1:
            raise ValueError("RSI MA length must be at least 1")
        self.rsi_ma_length = value
        self._save_config()
    
    def set_show_rsi_ma(self, value: bool):
        """Set show RSI MA flag."""
        self.show_rsi_ma = value
        self._save_config()
    
    def set_show_divergence(self, value: bool):
        """Set show divergence flag."""
        self.show_divergence = value
        self._save_config()
    
    def get_config(self) -> dict:
        """Get current runtime configuration."""
        return {
            "bypass_market_hours": self.bypass_market_hours,
            "use_mock_data": self.use_mock_data,
            "polling_interval_seconds": self.polling_interval_seconds,
            "historical_bars_count": self.historical_bars_count,
            "rsi_ma_type": self.rsi_ma_type,
            "rsi_ma_length": self.rsi_ma_length,
            "show_rsi_ma": self.show_rsi_ma,
            "show_divergence": self.show_divergence
        }


# Global runtime config instance
# Initialize with default polling interval of 30 seconds
runtime_config = RuntimeConfig(default_polling_interval=30)

