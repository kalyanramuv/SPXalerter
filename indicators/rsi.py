"""RSI indicator implementation using Wilder's smoothing method."""
from typing import List
from providers.base import Bar


class RSI:
    """RSI calculator using Wilder's smoothing method."""
    
    def __init__(self, period: int = 14):
        """
        Initialize RSI calculator.
        
        Args:
            period: RSI period (default 14)
        """
        self.period = period
    
    def calculate(self, bars: List[Bar]) -> List[float]:
        """
        Calculate RSI values for a series of bars.
        
        Args:
            bars: List of Bar objects (must be sorted by timestamp)
            
        Returns:
            List of RSI values (same length as bars, None for insufficient data)
        """
        if len(bars) < self.period + 1:
            return [None] * len(bars)
        
        # Extract closing prices
        closes = [bar.close for bar in bars]
        
        # Calculate price changes
        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        
        # Separate gains and losses
        gains = [delta if delta > 0 else 0.0 for delta in deltas]
        losses = [-delta if delta < 0 else 0.0 for delta in deltas]
        
        # Calculate initial average gain and loss (SMA)
        avg_gain = sum(gains[:self.period]) / self.period
        avg_loss = sum(losses[:self.period]) / self.period
        
        rsi_values = [None] * self.period
        
        # Calculate RS and RSI using Wilder's smoothing
        for i in range(self.period, len(gains)):
            # Wilder's smoothing: EMA-like calculation
            avg_gain = (avg_gain * (self.period - 1) + gains[i]) / self.period
            avg_loss = (avg_loss * (self.period - 1) + losses[i]) / self.period
            
            # Calculate RS and RSI
            if avg_loss == 0:
                rs = 100  # Avoid division by zero
            else:
                rs = avg_gain / avg_loss
            
            rsi = 100 - (100 / (1 + rs))
            rsi_values.append(rsi)
        
        # Pad with None for the first bar (no previous bar to calculate delta)
        return [None] + rsi_values
    
    def get_latest(self, bars: List[Bar]) -> float:
        """
        Get the latest RSI value.
        
        Args:
            bars: List of Bar objects
            
        Returns:
            Latest RSI value or None if insufficient data
        """
        rsi_values = self.calculate(bars)
        return rsi_values[-1] if rsi_values else None





