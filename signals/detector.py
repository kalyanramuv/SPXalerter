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
    BULLISH_DIVERGENCE = "bullish_divergence"
    BEARISH_DIVERGENCE = "bearish_divergence"


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
        
        # Detect divergences for each timeframe
        for timeframe in self.timeframes:
            if timeframe in bars_by_timeframe:
                bars = bars_by_timeframe[timeframe]
                if len(bars) >= 20:  # Need enough bars for divergence detection
                    divergence_signals = self._detect_divergences(timeframe, bars, current_rsi)
                    signals.extend(divergence_signals)
        
        return signals
    
    def _create_signal(
        self,
        signal_type: SignalType,
        timeframe: str,
        rsi_value: float,
        bars: List[Bar],
        all_rsi: Dict[str, Optional[float]],
        bar_index: Optional[int] = None
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
        # Use timestamp of the specific bar where signal was detected, or last bar if not specified
        if bar_index is not None and bars and 0 <= bar_index < len(bars):
            timestamp = bars[bar_index].timestamp
        else:
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
    
    def _detect_divergences(
        self,
        timeframe: str,
        bars: List[Bar],
        all_rsi: Dict[str, Optional[float]]
    ) -> List[Signal]:
        """
        Detect bullish and bearish divergences based on RSI and price pivot points.
        Based on Pine Script logic.
        
        Args:
            timeframe: Timeframe being analyzed
            bars: List of bars for the timeframe
            all_rsi: RSI values for all timeframes
            
        Returns:
            List of divergence signals
        """
        signals = []
        if len(bars) < 20:
            return signals
        
        # Calculate RSI for all bars
        rsi_values = self.rsi.calculate(bars)
        if len(rsi_values) < 20:
            return signals
        
        lookback_left = 5
        lookback_right = 5
        range_upper = 60
        range_lower = 5
        
        # Helper: check if bar i is a pivot low in RSI
        def is_pivot_low(values, i, lookback_left, lookback_right):
            if i < lookback_right or i >= len(values) - lookback_left:
                return False
            if values[i] is None:
                return False
            pivot_val = values[i]
            for j in range(i - lookback_right, i + lookback_left + 1):
                if j != i and j >= 0 and j < len(values) and values[j] is not None:
                    if values[j] <= pivot_val:
                        return False
            return True
        
        # Helper: check if bar i is a pivot high in RSI
        def is_pivot_high(values, i, lookback_left, lookback_right):
            if i < lookback_right or i >= len(values) - lookback_left:
                return False
            if values[i] is None:
                return False
            pivot_val = values[i]
            for j in range(i - lookback_right, i + lookback_left + 1):
                if j != i and j >= 0 and j < len(values) and values[j] is not None:
                    if values[j] >= pivot_val:
                        return False
            return True
        
        # Helper: find previous pivot low
        def find_prev_pivot_low(values, start_idx, lookback_left, lookback_right):
            for i in range(start_idx - 1, lookback_right - 1, -1):
                if is_pivot_low(values, i, lookback_left, lookback_right):
                    return i, start_idx - i
            return None, None
        
        # Helper: find previous pivot high
        def find_prev_pivot_high(values, start_idx, lookback_left, lookback_right):
            for i in range(start_idx - 1, lookback_right - 1, -1):
                if is_pivot_high(values, i, lookback_left, lookback_right):
                    return i, start_idx - i
            return None, None
        
        # Check recent bars (last 100 to avoid re-detecting old divergences)
        check_start = max(lookback_right, len(bars) - 100)
        check_end = len(bars) - lookback_left
        
        # Detect bullish divergence (RSI higher low, price lower low)
        for i in range(check_start, check_end):
            pivot_idx = i - lookback_right
            if pivot_idx < 0 or pivot_idx >= len(bars) or pivot_idx >= len(rsi_values):
                continue
            
            if not is_pivot_low(rsi_values, pivot_idx, lookback_left, lookback_right):
                continue
            
            current_rsi = rsi_values[pivot_idx]
            current_price = bars[pivot_idx].low
            
            prev_pivot_idx, bars_since = find_prev_pivot_low(rsi_values, pivot_idx, lookback_left, lookback_right)
            if prev_pivot_idx is None or not (range_lower <= bars_since <= range_upper):
                continue
            
            prev_rsi = rsi_values[prev_pivot_idx]
            prev_price = bars[prev_pivot_idx].low
            
            if current_rsi > prev_rsi and current_price < prev_price:
                signals.append(self._create_signal(
                    SignalType.BULLISH_DIVERGENCE,
                    timeframe,
                    current_rsi,
                    bars,
                    all_rsi,
                    bar_index=i
                ))
        
        # Detect bearish divergence (RSI lower high, price higher high)
        for i in range(check_start, check_end):
            pivot_idx = i - lookback_right
            if pivot_idx < 0 or pivot_idx >= len(bars) or pivot_idx >= len(rsi_values):
                continue
            
            if not is_pivot_high(rsi_values, pivot_idx, lookback_left, lookback_right):
                continue
            
            current_rsi = rsi_values[pivot_idx]
            current_price = bars[pivot_idx].high
            
            prev_pivot_idx, bars_since = find_prev_pivot_high(rsi_values, pivot_idx, lookback_left, lookback_right)
            if prev_pivot_idx is None or not (range_lower <= bars_since <= range_upper):
                continue
            
            prev_rsi = rsi_values[prev_pivot_idx]
            prev_price = bars[prev_pivot_idx].high
            
            if current_rsi < prev_rsi and current_price > prev_price:
                signals.append(self._create_signal(
                    SignalType.BEARISH_DIVERGENCE,
                    timeframe,
                    current_rsi,
                    bars,
                    all_rsi,
                    bar_index=i
                ))
        
        return signals

