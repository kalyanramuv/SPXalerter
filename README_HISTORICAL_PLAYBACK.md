# Historical Data Playback Setup

This guide explains how to use historical intraday data from Tradier for testing and simulating real-time alerts.

## Overview

The historical playback feature allows you to:
1. Download historical intraday data from Tradier
2. Save it to JSON files
3. Play it back in real-time simulation mode to test alert generation

## Step 1: Export Historical Data

Run the export script to download historical data from Tradier:

```bash
python scripts/export_historical_data.py --symbol SPY --timeframes 1min 5min 30min --count 2000 --output-dir historical_data
```

**Parameters:**
- `--symbol`: Trading symbol (default: SPY)
- `--timeframes`: Timeframes to export (default: 1min 5min 30min)
- `--count`: Number of bars per timeframe (default: 2000)
- `--output-dir`: Output directory for JSON files (default: historical_data)

**Output:**
The script creates JSON files in the `historical_data/` directory:
- `SPY_1min.json`
- `SPY_5min.json`
- `SPY_30min.json`

Each file contains an array of bars with the following format:
```json
[
  {
    "timestamp": "2024-01-15T09:30:00",
    "open": 485.50,
    "high": 485.75,
    "low": 485.25,
    "close": 485.60,
    "volume": 1234567
  },
  ...
]
```

## Step 2: Enable Historical Playback Mode

Set the environment variable to enable playback mode:

**Windows (PowerShell):**
```powershell
$env:USE_HISTORICAL_PLAYBACK="true"
python main.py
```

**Windows (Command Prompt):**
```cmd
set USE_HISTORICAL_PLAYBACK=true
python main.py
```

**Linux/Mac:**
```bash
export USE_HISTORICAL_PLAYBACK=true
python main.py
```

Or set it in your `.env` file:
```
USE_HISTORICAL_PLAYBACK=true
HISTORICAL_DATA_DIR=historical_data  # Optional, defaults to "historical_data"
```

## Step 3: Run the Application

Start the application as normal:

```bash
python main.py
```

The application will:
- Load historical data from JSON files
- Progressively feed bars to simulate real-time updates
- Generate alerts based on the historical data
- Display everything in the web dashboard

## How It Works

1. **Initial Load**: On startup, the `HistoricalPlaybackProvider` loads all historical bars from JSON files
2. **Progressive Playback**: Each polling cycle, `get_historical_bars()` returns bars up to the current position
3. **Position Advancement**: The position advances by 1 bar per polling cycle, simulating real-time updates
4. **Continuous Loop**: When reaching the end of the data, it loops back to the beginning

## Configuration

- **Polling Interval**: Control playback speed via the web UI (Controls → Polling Interval)
  - Lower interval = faster playback
  - Higher interval = slower playback
  
- **Historical Bars Count**: Adjust how many bars are kept in memory (affects initial load)

## Troubleshooting

**Problem**: "Historical data file not found"
- **Solution**: Make sure you've run the export script first and the JSON files are in the correct directory

**Problem**: No alerts appearing
- **Solution**: Check that your historical data contains periods with RSI values that would trigger alerts (oversold/overbought conditions)

**Problem**: Playback too fast/slow
- **Solution**: Adjust the polling interval in the web UI to control playback speed

## Notes

- The playback mode simulates real-time updates but uses historical data
- Alerts are generated based on the historical data patterns
- The system loops back to the beginning when it reaches the end of the data
- All alerts, charts, and RSI calculations work the same as with live data

