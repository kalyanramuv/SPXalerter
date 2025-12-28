# RSI Live Alerter (SPY)

Real-time RSI exhaustion and reclaim alerts with multi-timeframe confirmation for SPY.

## Features

- **Multi-Timeframe RSI**: Monitors 1-minute, 5-minute, and 30-minute timeframes (configurable)
- **Wilder's Method**: Accurate RSI(14) calculation using Wilder's smoothing
- **Signal Types**:
  - Oversold (RSI ≤ 30)
  - Overbought (RSI ≥ 70)
  - Bullish Reclaim (RSI crosses 30 → 35)
  - Bearish Reclaim (RSI crosses 70 → 65)
- **Multi-Timeframe Confirmation**: Signals require alignment across timeframes
- **Alert Delivery**:
  - FastAPI dashboard with real-time WebSocket updates
  - Discord webhooks (optional)
- **Reliability Features**:
  - Duplicate alert prevention
  - Cooldown windows (default 5 minutes)
  - Market hours detection

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configuration

Set environment variables:

```bash
# Required
export TRADIER_API_KEY=your_api_key_here
export TRADIER_ACCOUNT_ID=your_account_id  # Optional for data only

# Optional
export TRADIER_BASE_URL=https://sandbox.tradier.com/v1  # Or https://api.tradier.com/v1 for production
export SYMBOL=SPY  # Default: SPY
export POLLING_INTERVAL_SECONDS=20  # Default: 20 (seconds between polls)
export TIMEFRAMES=1min,5min,30min  # Comma-separated timeframes (default: 1min,5min,30min)
export ALERT_COOLDOWN_SECONDS=300  # Default: 300 (5 minutes)
export HISTORICAL_BARS_COUNT=2000  # Number of historical bars to fetch (default: 2000)
export BYPASS_MARKET_HOURS=true  # Allow testing outside market hours (default: false)

# Discord (optional)
export DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

Or create a `.env` file:

```env
TRADIER_API_KEY=your_api_key_here
TRADIER_ACCOUNT_ID=your_account_id
TRADIER_BASE_URL=https://sandbox.tradier.com/v1  # Or https://api.tradier.com/v1 for production
POLLING_INTERVAL_SECONDS=20  # Seconds between polls
TIMEFRAMES=1min,5min,30min  # Comma-separated timeframes to monitor
HISTORICAL_BARS_COUNT=2000  # Number of historical bars to fetch
BYPASS_MARKET_HOURS=true  # Set to true for testing outside market hours
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

### 3. Run

```bash
python main.py
```

The application will:
1. Start the FastAPI dashboard at `http://localhost:8000`
2. Begin polling market data and detecting RSI signals
3. Display alerts in the web dashboard
4. Send alerts to Discord (if configured)

## Usage

### Web Dashboard

Open `http://localhost:8000` in your browser to see:
- Real-time alerts with WebSocket updates
- Alert history
- RSI values and confirmation status

### API Endpoints

- `GET /`: Dashboard HTML
- `GET /api/alerts`: Get recent alerts (JSON)
- `WebSocket /ws`: Real-time alert stream

## Architecture

```
├── config.py          # Configuration management
├── engine.py          # Main RSI alerting engine
├── main.py            # Entry point
├── providers/         # Market data providers
│   ├── base.py       # Provider interface
│   └── tradier.py    # Tradier implementation
├── indicators/        # Technical indicators
│   └── rsi.py        # RSI calculator (Wilder's method)
├── signals/          # Signal detection
│   └── detector.py   # Multi-timeframe signal detector
├── alerts/           # Alert management
│   ├── manager.py    # Alert manager (cooldown, duplicates)
│   └── discord.py    # Discord integration
└── api/              # FastAPI dashboard
    └── main.py       # API routes and WebSocket
```

## Performance Targets

- Polling interval: ≤ 20 seconds
- Alert latency: ≤ 30 seconds
- RSI computation: < 10ms

## Future Enhancements

- ES futures confirmation
- Divergence detection
- Automated execution (out of scope for v1)
- Additional market data providers (Schwab, etc.)

## License

MIT



