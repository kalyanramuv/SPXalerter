"""Base market data provider interface."""
from abc import ABC, abstractmethod
from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Bar:
    """OHLCV bar data."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class MarketDataProvider(ABC):
    """Abstract base class for market data providers."""
    
    @abstractmethod
    def get_historical_bars(
        self,
        symbol: str,
        interval: str,
        count: int = 100
    ) -> List[Bar]:
        """
        Fetch historical bar data.
        
        Args:
            symbol: Trading symbol (e.g., "SPY")
            interval: Time interval (e.g., "1min", "5min")
            count: Number of bars to fetch
            
        Returns:
            List of Bar objects, sorted by timestamp (oldest first)
        """
        pass
    
    @abstractmethod
    def get_latest_bar(
        self,
        symbol: str,
        interval: str
    ) -> Optional[Bar]:
        """
        Fetch the latest bar for a symbol.
        
        Args:
            symbol: Trading symbol
            interval: Time interval
            
        Returns:
            Latest Bar or None if unavailable
        """
        pass
    
    @abstractmethod
    def is_market_open(self) -> bool:
        """
        Check if market is currently open.
        
        Returns:
            True if market is open, False otherwise
        """
        pass



