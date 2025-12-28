"""Runtime configuration for the application."""
from typing import Optional, List, Dict
from datetime import datetime


class RuntimeConfig:
    """Runtime configuration that can be changed via API."""
    
    def __init__(self):
        self.bypass_market_hours: bool = False
        self.use_mock_data: bool = False
        self.rsi_history_1min: List[Dict] = []
        self.rsi_history_5min: List[Dict] = []
        self.rsi_history_30min: List[Dict] = []
        self.max_rsi_history = 2000
    
    def set_bypass_market_hours(self, value: bool):
        """Set bypass market hours flag."""
        self.bypass_market_hours = value
    
    def set_use_mock_data(self, value: bool):
        """Set use mock data flag."""
        self.use_mock_data = value
    
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
    
    def get_config(self) -> dict:
        """Get current runtime configuration."""
        return {
            "bypass_market_hours": self.bypass_market_hours,
            "use_mock_data": self.use_mock_data
        }


# Global runtime config instance
runtime_config = RuntimeConfig()

