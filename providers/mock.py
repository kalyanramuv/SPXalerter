"""Mock market data provider for testing."""
import random
from typing import List, Optional
from datetime import datetime, timedelta
from .base import MarketDataProvider, Bar


class MockProvider(MarketDataProvider):
    """Mock market data provider that generates simulated price data."""
    
    def __init__(self, symbol: str = "SPY", base_price: float = 500.0):
        """
        Initialize mock provider.
        
        Args:
            symbol: Trading symbol (default: SPY)
            base_price: Base price to simulate around (default: 500.0)
        """
        self.symbol = symbol
        self.base_price = base_price
        self.current_price = base_price
    
    def get_historical_bars(
        self,
        symbol: str,
        interval: str,
        count: int = 100
    ) -> List[Bar]:
        """
        Generate mock historical bars.
        
        Args:
            symbol: Trading symbol
            interval: Time interval (e.g., "1min", "5min")
            count: Number of bars to generate
            
        Returns:
            List of Bar objects with simulated price data
        """
        bars = []
        now = datetime.now()
        
        # Determine minutes per bar
        if interval == "1min":
            minutes_per_bar = 1
        elif interval == "5min":
            minutes_per_bar = 5
        elif interval == "30min":
            minutes_per_bar = 30
        else:
            minutes_per_bar = 1
        
        # Generate bars going backwards in time
        price = self.base_price
        
        for i in range(count):
            # Calculate timestamp (most recent first)
            timestamp = now - timedelta(minutes=minutes_per_bar * (count - i - 1))
            
            # Simulate price movement with random walk
            change_pct = random.uniform(-0.002, 0.002)  # ±0.2% per bar
            price = price * (1 + change_pct)
            
            # Generate OHLC with some variation
            high = price * random.uniform(1.0, 1.001)
            low = price * random.uniform(0.999, 1.0)
            open_price = price * random.uniform(0.9995, 1.0005)
            close_price = price
            
            # Generate volume (random between 100k and 10M)
            volume = random.randint(100000, 10000000)
            
            bars.append(Bar(
                timestamp=timestamp,
                open=round(open_price, 2),
                high=round(high, 2),
                low=round(low, 2),
                close=round(close_price, 2),
                volume=volume
            ))
            
            price = close_price
        
        # Update current price
        self.current_price = price
        
        return bars
    
    def get_latest_bar(
        self,
        symbol: str,
        interval: str
    ) -> Optional[Bar]:
        """
        Get the latest mock bar.
        
        Args:
            symbol: Trading symbol
            interval: Time interval
            
        Returns:
            Latest Bar with simulated price
        """
        # Small random walk
        change_pct = random.uniform(-0.001, 0.001)
        self.current_price = self.current_price * (1 + change_pct)
        
        now = datetime.now()
        return Bar(
            timestamp=now,
            open=round(self.current_price, 2),
            high=round(self.current_price * 1.0005, 2),
            low=round(self.current_price * 0.9995, 2),
            close=round(self.current_price, 2),
            volume=random.randint(100000, 5000000)
        )
    
    def is_market_open(self) -> bool:
        """
        Mock market is always "open" (for testing purposes).
        
        Returns:
            True (market is always open in mock mode)
        """
        return True

