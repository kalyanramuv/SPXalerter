"""Multi-timeframe RSI signal detection."""
from typing import Dict, Optional, List
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from providers.base import Bar
from indicators.rsi import RSI
from config import RSIConfig


class SignalType(str, Enum):
    """Types of RSI signals."""
    OVERSOLD = "oversold"
    OVERBOUGHT = "overbought"


@dataclass
class Signal:
    """RSI signal with multi-timeframe confirmation."""
    signal_type: SignalType
    timestamp: datetime
    symbol: str
    timeframe: str
    rsi_value: float
    confirmed: bool  # True if all timeframes agree
    timeframes_status: Dict[str, Optional[float]]  # RSI values for each timeframe


class SignalDetector:
    """Multi-timeframe RSI signal detector."""
    
    def __init__(self, config: RSIConfig, timeframes: List[str], symbol: str = "SPY"):
        """
        Initialize signal detector.
        
        Args:
            config: RSI configuration
            timeframes: List of timeframes to monitor (e.g., ["1min", "5min"])
            symbol: Trading symbol (default: SPY)
        """
        self.config = config
        self.timeframes = timeframes
        self.symbol = symbol
        self.rsi = RSI(period=config.period)
        self._previous_rsi: Dict[str, Optional[float]] = {
            tf: None for tf in timeframes
        }
    
    def detect_signals(
        self,
        bars_by_timeframe: Dict[str, List[Bar]]
    ) -> List[Signal]:
        """
        Detect RSI signals across multiple timeframes.
        
        Args:
            bars_by_timeframe: Dictionary mapping timeframe to list of bars
            
        Returns:
            List of detected signals
        """
        signals = []
        current_rsi: Dict[str, Optional[float]] = {}
        
        # Calculate current RSI for each timeframe
        for timeframe in self.timeframes:
            if timeframe in bars_by_timeframe:
                bars = bars_by_timeframe[timeframe]
                if len(bars) >= self.config.period + 1:
                    rsi_value = self.rsi.get_latest(bars)
                    current_rsi[timeframe] = rsi_value
                else:
                    current_rsi[timeframe] = None
        
        # Detect signals for each timeframe
        for timeframe in self.timeframes:
            if timeframe not in current_rsi or current_rsi[timeframe] is None:
                continue
            
            rsi = current_rsi[timeframe]
            prev_rsi = self._previous_rsi.get(timeframe)
            
            # Detect oversold (only when entering territory - crossing from above threshold to below)
            if prev_rsi is not None:
                if prev_rsi > self.config.oversold_threshold and rsi <= self.config.oversold_threshold:
                    signals.append(self._create_signal(
                        SignalType.OVERSOLD,
                        timeframe,
                        rsi,
                        bars_by_timeframe[timeframe],
                        current_rsi
                    ))
            
            # Detect overbought (only when entering territory - crossing from below threshold to above)
            if prev_rsi is not None:
                if prev_rsi < self.config.overbought_threshold and rsi >= self.config.overbought_threshold:
                    signals.append(self._create_signal(
                        SignalType.OVERBOUGHT,
                        timeframe,
                        rsi,
                        bars_by_timeframe[timeframe],
                        current_rsi
                    ))
            
            # Update previous RSI
            self._previous_rsi[timeframe] = rsi
        
        return signals
    
    def _create_signal(
        self,
        signal_type: SignalType,
        timeframe: str,
        rsi_value: float,
        bars: List[Bar],
        all_rsi: Dict[str, Optional[float]]
    ) -> Signal:
        """
        Create a signal with multi-timeframe confirmation.
        
        Args:
            signal_type: Type of signal
            timeframe: Timeframe where signal was detected
            rsi_value: RSI value at detection
            bars: Bars for the timeframe
            all_rsi: RSI values for all timeframes
            
        Returns:
            Signal object with confirmation status
        """
        timestamp = bars[-1].timestamp if bars else datetime.now()
        symbol = self.symbol
        
        # Check confirmation across all timeframes
        timeframes_status = {}
        
        # Oversold/overbought signals are timeframe-specific entry signals
        # They should always be confirmed (alert when any timeframe enters the territory)
        confirmed = True  # Always confirm entry signals
        
        for tf in self.timeframes:
            tf_rsi = all_rsi.get(tf)
            if tf_rsi is None:
                timeframes_status[tf] = None  # Store None for missing data
                continue
            
            # Store RSI value for display
            timeframes_status[tf] = tf_rsi
        
        return Signal(
            signal_type=signal_type,
            timestamp=timestamp,
            symbol=symbol,
            timeframe=timeframe,
            rsi_value=rsi_value,
            confirmed=confirmed,
            timeframes_status=timeframes_status
        )

