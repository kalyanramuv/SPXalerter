"""Alert management with cooldown and duplicate prevention."""
from typing import Dict, Set, Optional
from datetime import datetime, timedelta
from signals.detector import Signal, SignalType
from config import AlertConfig


class AlertManager:
    """Manages alert delivery with cooldown and duplicate prevention."""
    
    def __init__(self, config: AlertConfig):
        """
        Initialize alert manager.
        
        Args:
            config: Alert configuration
        """
        self.config = config
        self.last_alert_time: Dict[SignalType, Optional[datetime]] = {
            signal_type: None for signal_type in SignalType
        }
        self.recent_signals: Set[str] = set()  # Track recent signals to prevent duplicates
    
    def should_send_alert(self, signal: Signal) -> bool:
        """
        Check if alert should be sent (cooldown and duplicate check).
        
        Args:
            signal: Signal to check
            
        Returns:
            True if alert should be sent
        """
        # Only send confirmed signals
        if not signal.confirmed:
            return False
        
        # For divergence signals, skip cooldown (they're unique events, duplicate detection is sufficient)
        is_divergence = signal.signal_type.value in ('bullish_divergence', 'bearish_divergence')
        if not is_divergence:
            # Check cooldown for oversold/overbought signals
            last_time = self.last_alert_time.get(signal.signal_type)
            if last_time:
                elapsed = (datetime.now() - last_time).total_seconds()
                if elapsed < self.config.cooldown_seconds:
                    return False
        
        # Check for duplicates
        # For divergences, use timestamp to avoid duplicates (same divergence detected multiple times)
        # For oversold/overbought, use signal type + timeframe
        is_divergence = signal.signal_type.value in ('bullish_divergence', 'bearish_divergence')
        if is_divergence:
            timestamp_minute = signal.timestamp.replace(second=0, microsecond=0)
            signal_key = f"{signal.signal_type}_{signal.timeframe}_{timestamp_minute.isoformat()}"
        else:
            signal_key = f"{signal.signal_type}_{signal.timeframe}"
        if signal_key in self.recent_signals:
            return False
        
        return True
    
    def record_alert(self, signal: Signal):
        """
        Record that an alert was sent.
        
        Args:
            signal: Signal that triggered the alert
        """
        self.last_alert_time[signal.signal_type] = datetime.now()
        # For divergences, use timestamp to avoid duplicates
        is_divergence = signal.signal_type.value in ('bullish_divergence', 'bearish_divergence')
        if is_divergence:
            timestamp_minute = signal.timestamp.replace(second=0, microsecond=0)
            signal_key = f"{signal.signal_type}_{signal.timeframe}_{timestamp_minute.isoformat()}"
        else:
            signal_key = f"{signal.signal_type}_{signal.timeframe}"
        self.recent_signals.add(signal_key)
        
        # Clean up old signal keys (keep only recent ones)
        # This set will grow, but with cooldown it should be manageable
        # In production, could implement a time-based cleanup
    
    def get_alert_message(self, signal: Signal) -> str:
        """
        Generate human-readable alert message.
        
        Args:
            signal: Signal to format
            
        Returns:
            Formatted alert message
        """
        signal_names = {
            SignalType.OVERSOLD: "🔻 OVERSOLD",
            SignalType.OVERBOUGHT: "🔺 OVERBOUGHT",
            SignalType.BULLISH_DIVERGENCE: "📈 BULLISH DIVERGENCE",
            SignalType.BEARISH_DIVERGENCE: "📉 BEARISH DIVERGENCE"
        }
        
        name = signal_names.get(signal.signal_type, signal.signal_type.value.upper())
        timeframes_str = ", ".join([
            f"{tf}: {rsi:.2f}" if rsi is not None and isinstance(rsi, (int, float)) else f"{tf}: N/A"
            for tf, rsi in signal.timeframes_status.items()
        ])
        
        return (
            f"{name} - {signal.symbol}\n"
            f"RSI: {signal.rsi_value:.2f} ({signal.timeframe})\n"
            f"Timeframes: {timeframes_str}\n"
            f"Confirmed: {'✅' if signal.confirmed else '❌'}\n"
            f"Time: {signal.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        )

