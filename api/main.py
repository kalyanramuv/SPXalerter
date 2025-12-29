"""FastAPI dashboard for RSI alerts."""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi import Request
from typing import List, Dict
from datetime import datetime
from signals.detector import Signal
from alerts.storage import AlertStorage
from api.runtime_config import runtime_config
from providers.base import Bar
from config import AppConfig
import json
import asyncio


app = FastAPI(title="RSI Live Alerter")

# Global event loop reference for scheduling async tasks from sync context
_loop: asyncio.AbstractEventLoop = None

# Persistent storage for alerts
alert_storage = AlertStorage(storage_file="alerts_history.json")
MAX_ALERTS = 100

# In-memory cache for quick access (loaded from persistent storage)
recent_alerts: List[dict] = []

# WebSocket connections
active_connections: List[WebSocket] = []

# Latest market data (price, RSI) for charting
latest_market_data: dict = {
    "timestamp": None,
    "price": None,
    "rsi": {}  # {timeframe: rsi_value}
}

# Store historical bars for all timeframes (for candlestick chart)
historical_bars: Dict[str, List[dict]] = {}  # {timeframe: [bars]}

# Load alerts from persistent storage on startup
def _load_alerts_from_storage():
    """Load alerts from persistent storage."""
    global recent_alerts
    recent_alerts = alert_storage.load_alerts(max_alerts=MAX_ALERTS)
    print(f"Loaded {len(recent_alerts)} alerts from persistent storage")

# Initialize on module load
_load_alerts_from_storage()


async def add_alert(signal: Signal, message: str):
    """Add alert to history and broadcast to WebSocket clients."""
    alert_data = {
        "signal_type": signal.signal_type.value,
        "timestamp": signal.timestamp.isoformat(),
        "symbol": signal.symbol,
        "timeframe": signal.timeframe,
        "rsi_value": signal.rsi_value,
        "confirmed": signal.confirmed,
        "timeframes_status": {
            k: v for k, v in signal.timeframes_status.items()
        },
        "message": message
    }
    
    # Save to persistent storage
    try:
        alert_storage.save_alert(alert_data)
    except Exception as e:
        print(f"Error saving alert to persistent storage: {e}")
    
    # Update in-memory cache
    recent_alerts.insert(0, alert_data)
    if len(recent_alerts) > MAX_ALERTS:
        recent_alerts.pop()
    
    # Broadcast to WebSocket clients
    for connection in active_connections.copy():
        try:
            await connection.send_json(alert_data)
        except:
            active_connections.remove(connection)


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the dashboard HTML."""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>RSI Live Alerter - SPY</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                margin: 0;
                padding: 20px;
                background: #1a1a1a;
                color: #e0e0e0;
            }
            .container {
                max-width: 1400px;
                margin: 0 auto;
                display: flex;
                flex-direction: column;
            }
            .main-content {
                display: flex;
                gap: 20px;
                align-items: flex-start;
            }
            .chart-section {
                flex: 1;
                min-width: 0;
            }
            .alerts-sidebar {
                width: 400px;
                flex-shrink: 0;
            }
            h1 {
                color: #4CAF50;
                border-bottom: 2px solid #4CAF50;
                padding-bottom: 10px;
            }
            .status {
                padding: 10px;
                margin: 10px 0;
                border-radius: 5px;
                background: #2a2a2a;
            }
            .status.connected {
                border-left: 4px solid #4CAF50;
            }
            .status.disconnected {
                border-left: 4px solid #f44336;
            }
            .alerts-sidebar {
                background: #2a2a2a;
                border-radius: 5px;
                padding: 15px;
                margin-top: 20px;
            }
            .alerts-sidebar h3 {
                color: #4CAF50;
                margin-top: 0;
                margin-bottom: 15px;
                font-size: 1.1em;
                border-bottom: 2px solid #4CAF50;
                padding-bottom: 10px;
            }
            .alerts {
                max-height: 700px;
                overflow-y: scroll;
                overflow-x: hidden;
                padding-right: 10px;
                scrollbar-width: thin;
                scrollbar-color: #4CAF50 #1a1a1a;
            }
            .alerts::-webkit-scrollbar {
                width: 10px;
            }
            .alerts::-webkit-scrollbar-track {
                background: #1a1a1a;
                border-radius: 5px;
                margin: 5px 0;
            }
            .alerts::-webkit-scrollbar-thumb {
                background: #4CAF50;
                border-radius: 5px;
                border: 2px solid #1a1a1a;
            }
            .alerts::-webkit-scrollbar-thumb:hover {
                background: #45a049;
            }
            .alert {
                padding: 15px;
                margin: 10px 0;
                border-radius: 5px;
                background: #2a2a2a;
                border-left: 4px solid #4CAF50;
                animation: slideIn 0.3s ease-out;
            }
            .alert.oversold { border-left-color: #2196F3; }
            .alert.overbought { border-left-color: #f44336; }
            @keyframes slideIn {
                from { transform: translateX(-20px); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            .alert-header {
                font-weight: bold;
                font-size: 1.2em;
                margin-bottom: 10px;
            }
            .alert-details {
                color: #b0b0b0;
                font-size: 0.9em;
            }
            .rsi-value {
                font-size: 1.5em;
                font-weight: bold;
                color: #4CAF50;
            }
            .chart-container {
                margin: 20px 0;
                padding: 15px;
                background: #2a2a2a;
                border-radius: 5px;
                height: 600px;
                position: relative;
            }
            .chart-title {
                color: #4CAF50;
                margin-bottom: 10px;
                font-size: 1.1em;
            }
            .chart-wrapper {
                position: relative;
                height: 60%;
            }
            .rsi-chart-wrapper {
                position: relative;
                height: 35%;
                margin-top: 10px;
                border-top: 1px solid #333;
                padding-top: 10px;
            }
            .rsi-chart-title {
                color: #2196F3;
                margin-bottom: 5px;
                font-size: 0.9em;
            }
            .rsi-controls {
                margin-top: 10px;
                padding: 10px;
                background: #1a1a1a;
                border-radius: 5px;
                display: flex;
                gap: 15px;
                align-items: center;
                flex-wrap: wrap;
            }
            .rsi-controls label {
                color: #e0e0e0;
                font-size: 0.9em;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            .rsi-controls input[type="number"] {
                background: #2a2a2a;
                border: 1px solid #444;
                color: #e0e0e0;
                padding: 5px 10px;
                border-radius: 3px;
                width: 60px;
                font-size: 0.9em;
            }
            .rsi-controls input[type="number"]:focus {
                outline: none;
                border-color: #4CAF50;
            }
            .rsi-controls select {
                background: #2a2a2a;
                border: 1px solid #444;
                color: #e0e0e0;
                padding: 5px 10px;
                border-radius: 3px;
                font-size: 0.85em;
                cursor: pointer;
            }
            .rsi-controls select:focus {
                outline: none;
                border-color: #4CAF50;
            }
        </style>
        <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/chartjs-chart-financial@0.2.1/dist/chartjs-chart-financial.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js"></script>
    </head>
    <body>
        <div class="container">
            <h1>📊 RSI Live Alerter - SPY</h1>
            <div id="status" class="status disconnected">Disconnected</div>
            
            <div class="controls" style="margin: 20px 0; padding: 15px; background: #2a2a2a; border-radius: 5px;">
                <h3 style="margin-top: 0; color: #4CAF50;">Controls</h3>
                <div style="display: flex; gap: 15px; flex-wrap: wrap; align-items: center;">
                    <button id="bypassBtn" onclick="toggleBypassMarketHours()" style="padding: 10px 20px; background: #444; color: #e0e0e0; border: 2px solid #666; border-radius: 5px; cursor: pointer; font-size: 14px;">
                        Trade 24/7: <span id="bypassStatus">ON</span>
                    </button>
                    <button id="mockBtn" onclick="toggleMockData()" style="padding: 10px 20px; background: #444; color: #e0e0e0; border: 2px solid #666; border-radius: 5px; cursor: pointer; font-size: 14px;">
                        Simulate Data: <span id="mockStatus">OFF</span>
                    </button>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <label style="color: #e0e0e0; font-size: 14px;">Polling Interval (sec):</label>
                        <input type="number" id="pollingInterval" min="1" max="300" step="1" style="padding: 8px 12px; background: #2a2a2a; color: #e0e0e0; border: 2px solid #666; border-radius: 5px; width: 80px; font-size: 14px;">
                        <button onclick="setPollingInterval()" style="padding: 8px 15px; background: #4CAF50; color: #fff; border: none; border-radius: 5px; cursor: pointer; font-size: 14px; font-weight: bold;">
                            Set
                        </button>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <label style="color: #e0e0e0; font-size: 14px;">Historical Bars:</label>
                        <input type="number" id="historicalBarsCount" min="100" max="10000" step="100" style="padding: 8px 12px; background: #2a2a2a; color: #e0e0e0; border: 2px solid #666; border-radius: 5px; width: 100px; font-size: 14px;">
                        <button onclick="setHistoricalBarsCount()" style="padding: 8px 15px; background: #4CAF50; color: #fff; border: none; border-radius: 5px; cursor: pointer; font-size: 14px; font-weight: bold;">
                            Set
                        </button>
                    </div>
                </div>
            </div>
            
            <div class="main-content">
                <div class="chart-section">
                    <div class="chart-container">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                            <div style="display: flex; align-items: center; gap: 15px;">
                                <div class="chart-title" id="chartTitle">SPY candlestick chart</div>
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <label style="color: #e0e0e0; font-size: 0.9em;">Timeframe:</label>
                                    <select id="timeframeSelector" style="padding: 5px 10px; background: #2a2a2a; color: #e0e0e0; border: 1px solid #444; border-radius: 3px; font-size: 0.9em; cursor: pointer;">
                                        <option value="1min">1min</option>
                                        <option value="5min">5min</option>
                                        <option value="30min">30min</option>
                                    </select>
                                </div>
                            </div>
                            <div style="display: flex; gap: 10px;">
                                <button onclick="resetZoom()" style="padding: 5px 15px; background: #444; color: #e0e0e0; border: 1px solid #666; border-radius: 3px; cursor: pointer; font-size: 12px;">Reset Zoom</button>
                                <button onclick="zoomIn()" style="padding: 5px 15px; background: #444; color: #e0e0e0; border: 1px solid #666; border-radius: 3px; cursor: pointer; font-size: 12px;">Zoom In</button>
                                <button onclick="zoomOut()" style="padding: 5px 15px; background: #444; color: #e0e0e0; border: 1px solid #666; border-radius: 3px; cursor: pointer; font-size: 12px;">Zoom Out</button>
                            </div>
                        </div>
                        <div style="color: #b0b0b0; font-size: 0.85em; margin-bottom: 5px;">Drag to pan, Scroll to zoom, or use buttons</div>
                        <div class="chart-wrapper">
                            <canvas id="marketChart"></canvas>
                        </div>
                        <div class="rsi-chart-wrapper">
                            <div class="rsi-chart-title" id="rsiChartTitle">RSI</div>
                            <canvas id="rsiChart"></canvas>
                            <div class="rsi-controls">
                                <div style="display: flex; gap: 15px; flex-wrap: wrap; align-items: flex-start;">
                                    <div style="border-left: 1px solid #444; padding-left: 15px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
                                        <label>
                                            Oversold:
                                            <input type="number" id="oversoldLevel" value="30" min="0" max="100" step="1">
                                        </label>
                                        <label>
                                            Overbought:
                                            <input type="number" id="overboughtLevel" value="70" min="0" max="100" step="1">
                                        </label>
                                    </div>
                                    <div style="border-left: 1px solid #444; padding-left: 15px; display: flex; gap: 10px; align-items: center;">
                                        <label style="color: #e0e0e0; font-size: 0.9em; display: flex; align-items: center; gap: 5px; cursor: pointer;">
                                            <input type="checkbox" id="showMAToggle" style="cursor: pointer;">
                                            <span>Show Moving Average</span>
                                        </label>
                                    </div>
                                    <div style="border-left: 1px solid #444; padding-left: 15px; display: flex; gap: 10px; align-items: center;">
                                        <label style="color: #e0e0e0; font-size: 0.9em; display: flex; align-items: center; gap: 5px; cursor: pointer;">
                                            <input type="checkbox" id="divergenceToggle" style="cursor: pointer;">
                                            <span>Show Divergence</span>
                                        </label>
                                    </div>
                                </div>
                                <div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid #444; display: flex; gap: 20px; flex-wrap: wrap; align-items: center;">
                                    <div style="display: flex; gap: 15px; align-items: center; flex-wrap: wrap;">
                                        <div style="display: flex; gap: 8px; align-items: center;">
                                            <label style="color: #e0e0e0; font-size: 0.85em;">MA Type:</label>
                                            <select id="rsiMAType" style="padding: 4px 8px; background: #2a2a2a; color: #e0e0e0; border: 1px solid #444; border-radius: 3px; font-size: 0.85em; cursor: pointer;">
                                                <option value="None">None</option>
                                                <option value="SMA">SMA</option>
                                                <option value="EMA">EMA</option>
                                                <option value="RMA">RMA</option>
                                                <option value="WMA">WMA</option>
                                            </select>
                                            <label style="color: #e0e0e0; font-size: 0.85em;">Length:</label>
                                            <input type="number" id="rsiMALength" value="14" min="1" max="200" step="1" style="padding: 4px 8px; background: #2a2a2a; color: #e0e0e0; border: 1px solid #444; border-radius: 3px; width: 60px; font-size: 0.85em;">
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="alerts-sidebar">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; border-bottom: 2px solid #4CAF50; padding-bottom: 10px;">
                        <h3 style="margin: 0; color: #4CAF50; font-size: 1.1em;">📊 Alerts</h3>
                        <button onclick="clearAlerts()" style="padding: 5px 12px; background: #f44336; color: #fff; border: none; border-radius: 3px; cursor: pointer; font-size: 12px; font-weight: bold;">
                            Clear All
                        </button>
                    </div>
            <div class="alerts" id="alerts"></div>
                </div>
            </div>
        </div>
        <script>
            const statusDiv = document.getElementById('status');
            const alertsDiv = document.getElementById('alerts');
            
            // Setup WebSocket connection
            let ws = null;
            function connectWebSocket() {
                try {
                    // Auto-detect WebSocket protocol (ws:// for HTTP, wss:// for HTTPS)
                    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                    ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws`);
            
            ws.onopen = () => {
                statusDiv.textContent = '✅ Connected - Listening for alerts...';
                statusDiv.className = 'status connected';
            };
            
            ws.onclose = () => {
                statusDiv.textContent = '❌ Disconnected - Reconnecting...';
                statusDiv.className = 'status disconnected';
                        // Reconnect after 3 seconds
                        setTimeout(connectWebSocket, 3000);
                    };
                    
                    ws.onerror = (error) => {
                        console.error('WebSocket error:', error);
                        statusDiv.textContent = '❌ Connection Error';
                        statusDiv.className = 'status disconnected';
            };
            
            ws.onmessage = (event) => {
                        try {
                const alert = JSON.parse(event.data);
                addAlert(alert);
                        } catch (e) {
                            console.error('Error parsing alert:', e);
                        }
                    };
                } catch (error) {
                    console.error('Error creating WebSocket:', error);
                    statusDiv.textContent = '❌ Connection Error';
                    statusDiv.className = 'status disconnected';
                }
            }
            
            // Connect WebSocket
            connectWebSocket();
            
            // Candlestick chart setup
            const chartCtx = document.getElementById('marketChart').getContext('2d');
            const rsiChartCtx = document.getElementById('rsiChart').getContext('2d');
            let marketChart = null;
            let rsiChart = null;
            let allCandlestickData = [];
            let selectedTimeframe = '1min'; // Default timeframe
            let availableTimeframes = ['1min', '5min', '30min']; // Will be loaded from API
            
            // MA calculation functions
            function calculateSMA(values, period) {
                if (values.length < period) return [];
                const result = [];
                for (let i = period - 1; i < values.length; i++) {
                    let sum = 0;
                    for (let j = i - period + 1; j <= i; j++) {
                        sum += values[j];
                    }
                    result.push(sum / period);
                }
                return result;
            }
            
            function calculateEMA(values, period) {
                if (values.length < period) return [];
                const result = [];
                const multiplier = 2 / (period + 1);
                // Start with SMA for first value
                let sum = 0;
                for (let i = 0; i < period; i++) {
                    sum += values[i];
                }
                result.push(sum / period);
                // Calculate EMA for remaining values
                for (let i = period; i < values.length; i++) {
                    const ema = (values[i] - result[result.length - 1]) * multiplier + result[result.length - 1];
                    result.push(ema);
                }
                return result;
            }
            
            function calculateRMA(values, period) {
                if (values.length < period) return [];
                const result = [];
                // Start with SMA for first value
                let sum = 0;
                for (let i = 0; i < period; i++) {
                    sum += values[i];
                }
                result.push(sum / period);
                // Calculate RMA (Wilder's smoothing) for remaining values
                for (let i = period; i < values.length; i++) {
                    const rma = (values[i] + result[result.length - 1] * (period - 1)) / period;
                    result.push(rma);
                }
                return result;
            }
            
            function calculateWMA(values, period) {
                if (values.length < period) return [];
                const result = [];
                for (let i = period - 1; i < values.length; i++) {
                    let sum = 0;
                    let weightSum = 0;
                    for (let j = 0; j < period; j++) {
                        const weight = period - j;
                        sum += values[i - j] * weight;
                        weightSum += weight;
                    }
                    result.push(sum / weightSum);
                }
                return result;
            }
            
            function calculateMA(rsiDataPoints, maType, maLength) {
                if (maType === 'None' || !rsiDataPoints || rsiDataPoints.length === 0) return null;
                if (rsiDataPoints.length < maLength) return null;
                
                const values = rsiDataPoints.map(d => d.y);
                let maValues = [];
                
                switch (maType) {
                    case 'SMA':
                        maValues = calculateSMA(values, maLength);
                        break;
                    case 'EMA':
                        maValues = calculateEMA(values, maLength);
                        break;
                    case 'RMA':
                        maValues = calculateRMA(values, maLength);
                        break;
                    case 'WMA':
                        maValues = calculateWMA(values, maLength);
                        break;
                    default:
                        return null;
                }
                
                // Map MA values back to data points (align with RSI data, offset by period)
                const maData = [];
                for (let i = 0; i < maValues.length; i++) {
                    const rsiIndex = i + maLength - 1; // Offset to align with RSI data
                    if (rsiIndex < rsiDataPoints.length) {
                        maData.push({
                            x: rsiDataPoints[rsiIndex].x,
                            y: maValues[i],
                            t: rsiDataPoints[rsiIndex].t
                        });
                    }
                }
                
                return maData.length > 0 ? maData : null;
            }
            
            
            // Divergence detection function (based on Pine Script logic)
            function detectDivergence(rsiData, priceData) {
                if (!rsiData || !priceData || rsiData.length < 20 || priceData.length < 20) return [];
                
                const lookbackLeft = 5;
                const lookbackRight = 5;
                const divergences = [];
                
                // Find pivot lows (for bullish divergence)
                for (let i = lookbackRight; i < rsiData.length - lookbackLeft; i++) {
                    // Check if this is a pivot low in RSI
                    let isPivotLowRSI = true;
                    for (let j = i - lookbackRight; j <= i + lookbackLeft; j++) {
                        if (j !== i && rsiData[j] && rsiData[i] && rsiData[j].y <= rsiData[i].y) {
                            isPivotLowRSI = false;
                            break;
                        }
                    }
                    
                    if (isPivotLowRSI && rsiData[i] && priceData[rsiData[i].x]) {
                        // Find previous pivot low
                        for (let prevIdx = i - lookbackRight - 5; prevIdx >= lookbackRight; prevIdx--) {
                            if (!rsiData[prevIdx]) continue;
                            
                            let isPrevPivotLowRSI = true;
                            for (let j = prevIdx - lookbackRight; j <= prevIdx + lookbackLeft; j++) {
                                if (j !== prevIdx && rsiData[j] && rsiData[prevIdx] && 
                                    (j < 0 || j >= rsiData.length || rsiData[j].y <= rsiData[prevIdx].y)) {
                                    isPrevPivotLowRSI = false;
                                    break;
                                }
                            }
                            
                            if (isPrevPivotLowRSI && rsiData[prevIdx] && priceData[rsiData[prevIdx].x]) {
                                const currentRSI = rsiData[i].y;
                                const prevRSI = rsiData[prevIdx].y;
                                const currentPrice = priceData[rsiData[i].x].l; // Use low for pivot low
                                const prevPrice = priceData[rsiData[prevIdx].x].l;
                                
                                // Bullish divergence: RSI higher low, price lower low
                                if (currentRSI > prevRSI && currentPrice < prevPrice) {
                                    divergences.push({
                                        type: 'bullish',
                                        index: rsiData[i].x,
                                        rsiValue: currentRSI
                                    });
                                }
                                break; // Found previous pivot, move on
                            }
                        }
                    }
                }
                
                // Find pivot highs (for bearish divergence)
                for (let i = lookbackRight; i < rsiData.length - lookbackLeft; i++) {
                    // Check if this is a pivot high in RSI
                    let isPivotHighRSI = true;
                    for (let j = i - lookbackRight; j <= i + lookbackLeft; j++) {
                        if (j !== i && rsiData[j] && rsiData[i] && rsiData[j].y >= rsiData[i].y) {
                            isPivotHighRSI = false;
                            break;
                        }
                    }
                    
                    if (isPivotHighRSI && rsiData[i] && priceData[rsiData[i].x]) {
                        // Find previous pivot high
                        for (let prevIdx = i - lookbackRight - 5; prevIdx >= lookbackRight; prevIdx--) {
                            if (!rsiData[prevIdx]) continue;
                            
                            let isPrevPivotHighRSI = true;
                            for (let j = prevIdx - lookbackRight; j <= prevIdx + lookbackLeft; j++) {
                                if (j !== prevIdx && rsiData[j] && rsiData[prevIdx] && 
                                    (j < 0 || j >= rsiData.length || rsiData[j].y >= rsiData[prevIdx].y)) {
                                    isPrevPivotHighRSI = false;
                                    break;
                                }
                            }
                            
                            if (isPrevPivotHighRSI && rsiData[prevIdx] && priceData[rsiData[prevIdx].x]) {
                                const currentRSI = rsiData[i].y;
                                const prevRSI = rsiData[prevIdx].y;
                                const currentPrice = priceData[rsiData[i].x].h; // Use high for pivot high
                                const prevPrice = priceData[rsiData[prevIdx].x].h;
                                
                                // Bearish divergence: RSI lower high, price higher high
                                if (currentRSI < prevRSI && currentPrice > prevPrice) {
                                    divergences.push({
                                        type: 'bearish',
                                        index: rsiData[i].x,
                                        rsiValue: currentRSI
                                    });
                                }
                                break; // Found previous pivot, move on
                            }
                        }
                    }
                }
                
                return divergences;
            }
            
            // RSI plugin registration is handled by ensureRSIPluginRegistered() function
            
            // Helper function to ensure RSI plugin is registered
            function ensureRSIPluginRegistered() {
                if (typeof Chart === 'undefined' || !Chart.registry) {
                    return false;
                }
                
                // Check if plugin is already registered (Chart.registry.getPlugin throws if not found)
                let pluginExists = false;
                try {
                    Chart.registry.getPlugin('rsiLevels');
                    pluginExists = true;
                } catch (e) {
                    // Plugin not registered yet
                    pluginExists = false;
                }
                
                if (!pluginExists) {
                    const rsiLevelsPlugin = {
                        id: 'rsiLevels',
                        afterDraw: (chart) => {
                            try {
                                const ctx = chart.ctx;
                                if (!chart.scales || !chart.scales.y || !chart.chartArea) return;
                                const yScale = chart.scales.y;
                                
                                const oversoldInput = document.getElementById('oversoldLevel');
                                const overboughtInput = document.getElementById('overboughtLevel');
                                const oversold = oversoldInput ? parseFloat(oversoldInput.value) || 30 : 30;
                                const overbought = overboughtInput ? parseFloat(overboughtInput.value) || 70 : 70;
                                
                                // Draw oversold line
                                const oversoldY = yScale.getPixelForValue(oversold);
                                if (!isNaN(oversoldY) && oversoldY >= chart.chartArea.top && oversoldY <= chart.chartArea.bottom) {
                                    ctx.save();
                                    ctx.strokeStyle = '#FFFFFF';
                                    ctx.lineWidth = 1.5;
                                    ctx.setLineDash([5, 5]);
                                    ctx.beginPath();
                                    ctx.moveTo(chart.chartArea.left, oversoldY);
                                    ctx.lineTo(chart.chartArea.right, oversoldY);
                                    ctx.stroke();
                                    ctx.restore();
                                    
                                    ctx.save();
                                    ctx.fillStyle = '#FFFFFF';
                                    ctx.font = 'bold 10px Arial';
                                    ctx.textAlign = 'right';
                                    ctx.fillText('Oversold ' + oversold, chart.chartArea.right - 5, oversoldY - 5);
                                    ctx.restore();
                                }
                                
                                // Draw overbought line
                                const overboughtY = yScale.getPixelForValue(overbought);
                                if (!isNaN(overboughtY) && overboughtY >= chart.chartArea.top && overboughtY <= chart.chartArea.bottom) {
                                    ctx.save();
                                    ctx.strokeStyle = '#FFFFFF';
                                    ctx.lineWidth = 1.5;
                                    ctx.setLineDash([5, 5]);
                                    ctx.beginPath();
                                    ctx.moveTo(chart.chartArea.left, overboughtY);
                                    ctx.lineTo(chart.chartArea.right, overboughtY);
                                    ctx.stroke();
                                    ctx.restore();
                                    
                                    ctx.save();
                                    ctx.fillStyle = '#FFFFFF';
                                    ctx.font = 'bold 10px Arial';
                                    ctx.textAlign = 'right';
                                    ctx.fillText('Overbought ' + overbought, chart.chartArea.right - 5, overboughtY - 5);
                                    ctx.restore();
                                }
                                
                                // Draw midline
                                const midY = yScale.getPixelForValue(50);
                                if (!isNaN(midY) && midY >= chart.chartArea.top && midY <= chart.chartArea.bottom) {
                                    ctx.save();
                                    ctx.strokeStyle = '#666';
                                    ctx.lineWidth = 1;
                                    ctx.setLineDash([3, 3]);
                                    ctx.beginPath();
                                    ctx.moveTo(chart.chartArea.left, midY);
                                    ctx.lineTo(chart.chartArea.right, midY);
                                    ctx.stroke();
                                    ctx.restore();
                                }
                            } catch (e) {
                                console.error('Error drawing RSI levels:', e);
                            }
                        }
                    };
                    Chart.register(rsiLevelsPlugin);
                    
                    // Register divergence plugin
                    const divergencePlugin = {
                        id: 'rsiDivergence',
                        afterDatasetsDraw: (chart) => {
                            try {
                                const divergenceToggle = document.getElementById('divergenceToggle');
                                if (!divergenceToggle || !divergenceToggle.checked) return;
                                
                                const ctx = chart.ctx;
                                if (!chart.scales || !chart.scales.x || !chart.scales.y || !chart.chartArea) return;
                                
                                // Get RSI dataset for selected timeframe (not MA)
                                const rsiDataset = chart.data.datasets.find(d => !d.isMA && d.timeframe === selectedTimeframe);
                                if (!rsiDataset || !rsiDataset.data || rsiDataset.data.length < 20) return;
                                
                                // Calculate divergence
                                const divergences = detectDivergence(rsiDataset.data, allCandlestickData);
                                
                                // Draw divergence markers
                                ctx.save();
                                divergences.forEach(div => {
                                    const xPos = chart.scales.x.getPixelForValue(div.index);
                                    const yPos = chart.scales.y.getPixelForValue(div.rsiValue);
                                    
                                    if (xPos >= chart.chartArea.left && xPos <= chart.chartArea.right &&
                                        yPos >= chart.chartArea.top && yPos <= chart.chartArea.bottom) {
                                        
                                        // Draw marker
                                        ctx.fillStyle = div.type === 'bullish' ? '#00FF00' : '#FF0000';
                                        ctx.beginPath();
                                        ctx.arc(xPos, yPos, 4, 0, Math.PI * 2);
                                        ctx.fill();
                                        
                                        // Draw label
                                        ctx.fillStyle = div.type === 'bullish' ? '#00FF00' : '#FF0000';
                                        ctx.font = 'bold 10px Arial';
                                        ctx.textAlign = 'center';
                                        const labelY = div.type === 'bullish' ? yPos - 12 : yPos + 12;
                                        ctx.fillText(div.type === 'bullish' ? 'Bull' : 'Bear', xPos, labelY);
                                    }
                                });
                                ctx.restore();
                            } catch (e) {
                                console.error('Error drawing divergence:', e);
                            }
                        }
                    };
                    Chart.register(divergencePlugin);
                    
                    return true;
                }
                return true; // Already registered
            }
            
            // Function to load and update candlestick chart
            async function loadCandlestickChart() {
                try {
                    if (typeof Chart === 'undefined' || typeof Chart.register === 'undefined') {
                        console.error('Chart.js is not loaded!');
                        return;
                    }
                    
                    const response = await fetch(`/api/bars/${selectedTimeframe}`);
                    const data = await response.json();
                    
                    if (!data.bars || data.bars.length === 0) {
                        console.log('No bars data available yet');
                        return;
                    }
                    
                    // Convert bars to candlestick format using index instead of timestamp to remove gaps
                    // Store timestamps separately for tooltip display
                    const newCandlestickData = data.bars.map((bar, index) => ({
                        x: index,
                        o: bar.open,
                        h: bar.high,
                        l: bar.low,
                        c: bar.close,
                        t: new Date(bar.timestamp) // Store timestamp for tooltip
                    }));
                    
                    // Preserve current zoom level if chart exists
                    // On initial load, show only the rightmost portion (latest ~200 bars) for auto-scroll
                    // On subsequent loads, preserve the current zoom level
                    let preservedMin = 0;
                    let preservedMax = newCandlestickData.length - 1;
                    const isInitialLoad = !marketChart;
                    
                    if (isInitialLoad && newCandlestickData.length > 0) {
                        // Show only the rightmost portion (latest 200 bars, or all if less than 200)
                        const visibleBars = Math.min(200, newCandlestickData.length);
                        preservedMin = Math.max(0, newCandlestickData.length - visibleBars);
                        preservedMax = newCandlestickData.length - 1;
                    } else if (!isInitialLoad && marketChart && marketChart.scales && marketChart.scales.x) {
                        // Preserve current zoom level
                        preservedMin = marketChart.scales.x.min;
                        preservedMax = marketChart.scales.x.max;
                        // Ensure preserved values are within valid range for new data
                        preservedMin = Math.max(0, Math.min(preservedMin, newCandlestickData.length - 1));
                        preservedMax = Math.max(preservedMin + 1, Math.min(preservedMax, newCandlestickData.length - 1));
                    }
                    
                    // Store previous data length to detect new candles
                    const previousDataLength = allCandlestickData.length;
                    
                    // Update the global data array
                    allCandlestickData = newCandlestickData;
                    
                    // If chart already exists, update it instead of recreating (preserves zoom)
                    if (marketChart && !isInitialLoad) {
                        // Check if we should auto-scroll (user is at rightmost position)
                        const wasAtRightmost = preservedMax >= (previousDataLength - 1.5); // Allow small tolerance
                        const hasNewData = newCandlestickData.length > previousDataLength;
                        
                        // Update chart data
                        marketChart.data.datasets[0].data = allCandlestickData;
                        // Update zoom limits for new data length
                        if (marketChart.options.plugins.zoom.zoom.limits) {
                            marketChart.options.plugins.zoom.zoom.limits.x.max = allCandlestickData.length - 1;
                        }
                        
                        // Auto-scroll to rightmost if user was already there and new data arrived
                        if (wasAtRightmost && hasNewData) {
                            // Auto-scroll to show latest data
                            preservedMax = allCandlestickData.length - 1;
                            // Keep the same zoom range (width of visible area)
                            const range = preservedMax - preservedMin;
                            preservedMin = Math.max(0, preservedMax - range);
                        } else {
                            // Preserve zoom level by setting min/max before update
                            preservedMin = Math.max(0, Math.min(preservedMin, allCandlestickData.length - 1));
                            preservedMax = Math.max(preservedMin + 1, Math.min(preservedMax, allCandlestickData.length - 1));
                        }
                        
                        marketChart.options.scales.x.min = preservedMin;
                        marketChart.options.scales.x.max = preservedMax;
                        // Update the chart (this preserves or updates zoom)
                        marketChart.update('none');
                        // Reload RSI chart to sync with updated data
                        loadRSIChart();
                        return; // Exit early, chart is updated
                    }
                    
                    // Destroy existing chart if it exists (should only happen on initial load or errors)
                    if (marketChart) {
                        marketChart.destroy();
                    }
                    
                    // Update chart title
                    const chartTitle = document.getElementById('chartTitle');
                    if (chartTitle) {
                        chartTitle.textContent = `SPY candlestick chart`;
                    }
                    
                    // Create new candlestick chart (only on initial load)
                    marketChart = new Chart(chartCtx, {
                        type: 'candlestick',
                        data: {
                            datasets: [{
                                label: `SPY ${selectedTimeframe}`,
                                data: allCandlestickData
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            layout: {
                                padding: 0  // No padding to ensure exact alignment
                            },
                            plugins: {
                                zoom: {
                                    pan: {
                                        enabled: true,
                                        mode: 'x',
                                        threshold: 10,
                                        modifierKey: null,
                                        onPan: function({chart}) {
                                            // Sync RSI chart when main chart is panned
                                            syncRSIChart();
                                        }
                                    },
                                    zoom: {
                                        wheel: {
                                            enabled: true,
                                            speed: 0.05,
                                            modifierKey: null
                                        },
                                        pinch: {
                                            enabled: true
                                        },
                                        drag: {
                                            enabled: true,
                                            modifierKey: null
                                        },
                                        mode: 'x',
                                        limits: {
                                            x: { min: 0, max: allCandlestickData.length - 1 }
                                        },
                                        onZoom: function({chart}) {
                                            // Sync RSI chart when main chart is zoomed
                                            syncRSIChart();
                                        }
                                    }
                                },
                                legend: {
                                    display: false
                                },
                                tooltip: {
                                    enabled: true,
                                    callbacks: {
                                        title: function(context) {
                                            const point = context[0].raw;
                                            if (point.t) {
                                                return point.t.toLocaleString();
                                            }
                                            return 'Bar ' + point.x;
                                        },
                                        label: function(context) {
                                            const point = context.raw;
                                            return [
                                                'O: $' + point.o.toFixed(2),
                                                'H: $' + point.h.toFixed(2),
                                                'L: $' + point.l.toFixed(2),
                                                'C: $' + point.c.toFixed(2)
                                            ];
                                        }
                                    }
                                }
                            },
                            scales: {
                                x: {
                                    type: 'linear',
                                    position: 'bottom',
                                    offset: false,  // Don't add padding that could cause misalignment
                                    ticks: { 
                                        color: '#b0b0b0',
                                        maxRotation: 45,
                                        minRotation: 45,
                                        stepSize: Math.max(1, Math.floor(allCandlestickData.length / 10)),
                                        callback: function(value, index, ticks) {
                                            const dataIndex = Math.round(value);
                                            if (dataIndex >= 0 && dataIndex < allCandlestickData.length) {
                                                const timestamp = allCandlestickData[dataIndex].t;
                                                return timestamp.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
                                            }
                                            return '';
                                        }
                                    },
                                    grid: { color: '#333' },
                                    min: preservedMin, // Preserve zoom level or show all data by default
                                    max: preservedMax
                                },
                                y: {
                                    ticks: { color: '#4CAF50' },
                                    grid: { color: '#333' },
                                    title: {
                                        display: true,
                                        text: 'Price ($)',
                                        color: '#4CAF50'
                                    }
                                }
                            }
                        }
                    });
                    
                    // Setup chart synchronization
                    setupChartSync();
                    
                    // Load and update RSI chart
                    loadRSIChart();
                } catch (error) {
                    console.error('Error loading candlestick chart:', error);
                }
            }
            
            // Function to load and update RSI chart
            async function loadRSIChart() {
                try {
                    if (typeof Chart === 'undefined' || typeof Chart.register === 'undefined') {
                        console.error('Chart.js is not loaded!');
                        return;
                    }
                    
                    const response = await fetch('/api/rsi-history');
                    const data = await response.json();
                    
                    // Get RSI data for selected timeframe
                    const rsiKey = `rsi_${selectedTimeframe}`;
                    const rsiDataForTimeframe = data[rsiKey] || [];
                    
                    if (!rsiDataForTimeframe || rsiDataForTimeframe.length === 0) {
                        console.log(`No RSI data available yet for ${selectedTimeframe}`);
                        return;
                    }
                    
                    // Update RSI chart title
                    const rsiChartTitle = document.getElementById('rsiChartTitle');
                    if (rsiChartTitle) {
                        rsiChartTitle.textContent = `RSI ${selectedTimeframe}`;
                    }
                    
                    // Create RSI chart data - align with main chart indices
                    const datasets = [];
                    
                    // Create a Set of valid candlestick indices for fast lookup
                    // This ensures RSI points only exist where candlesticks exist
                    const validCandlestickIndices = new Set();
                    for (let i = 0; i < allCandlestickData.length; i++) {
                        validCandlestickIndices.add(i);
                    }
                    
                    // Helper function to filter and map RSI data points
                    function createRSIDataset(rsiData, label, color, bgColor) {
                        if (!rsiData || rsiData.length === 0) return null;
                        
                        // Filter to only include points at valid candlestick indices
                        // Sort by index to ensure proper ordering
                        // Include timestamp for tooltip display
                        const filteredData = rsiData
                            .filter(point => validCandlestickIndices.has(point.index))
                            .sort((a, b) => a.index - b.index)
                            .map(point => {
                                // Get timestamp from candlestick data at the same index
                                const timestamp = (point.index >= 0 && point.index < allCandlestickData.length) 
                                    ? allCandlestickData[point.index].t 
                                    : null;
                                return { 
                                    x: point.index, 
                                    y: point.rsi,
                                    t: timestamp  // Store timestamp for tooltip
                                };
                            });
                        
                        if (filteredData.length === 0) return null;
                        
                        return {
                            label: label,
                            data: filteredData,
                            borderColor: color,
                            backgroundColor: bgColor,
                            tension: 0.1,
                            fill: false,
                            pointRadius: 0,
                            spanGaps: false  // Don't draw lines across gaps
                        };
                    }
                    
                    // Create RSI dataset for selected timeframe
                    const rsiColors = {
                        '1min': '#2196F3',
                        '5min': '#FF9800',
                        '30min': '#9C27B0'
                    };
                    const rsiBgColors = {
                        '1min': 'rgba(33, 150, 243, 0.1)',
                        '5min': 'rgba(255, 152, 0, 0.1)',
                        '30min': 'rgba(156, 39, 176, 0.1)'
                    };
                    
                    const rsiDataset = createRSIDataset(rsiDataForTimeframe, `RSI ${selectedTimeframe}`, 
                        rsiColors[selectedTimeframe] || '#2196F3', 
                        rsiBgColors[selectedTimeframe] || 'rgba(33, 150, 243, 0.1)');
                    if (rsiDataset) {
                        rsiDataset.timeframe = selectedTimeframe;
                        datasets.push(rsiDataset);
                        
                        // Add MA if enabled
                        const showMA = document.getElementById('showMAToggle')?.checked || false;
                        if (showMA) {
                            const maTypeSelect = document.getElementById('rsiMAType');
                            let maType = maTypeSelect?.value || 'None';
                            const maLength = parseInt(document.getElementById('rsiMALength')?.value || '14');
                            // If checkbox is checked but type is None, default to SMA
                            if (maType === 'None') {
                                maType = 'SMA';
                                if (maTypeSelect) {
                                    maTypeSelect.value = 'SMA';
                                }
                            }
                            if (maType !== 'None') {
                                console.log(`Calculating MA for ${selectedTimeframe}: type=${maType}, length=${maLength}, rsiDataPoints=${rsiDataset.data.length}`);
                                const maData = calculateMA(rsiDataset.data, maType, maLength);
                                if (maData && maData.length > 0) {
                                    console.log(`✓ Added MA dataset for ${selectedTimeframe}: type=${maType}, length=${maLength}, dataPoints=${maData.length}`);
                                    const maDataset = {
                                        label: `RSI ${selectedTimeframe} MA`,
                                        data: maData,
                                        borderColor: '#FFEB3B',
                                        backgroundColor: 'rgba(255, 235, 59, 0.1)',
                                        tension: 0.1,
                                        fill: false,
                                        pointRadius: 0,
                                        spanGaps: false,
                                        timeframe: selectedTimeframe,
                                        isMA: true,
                                        maType: maType,
                                        hidden: false
                                    };
                                    datasets.push(maDataset);
                                } else {
                                    console.warn(`✗ MA calculation returned no data for ${selectedTimeframe}: type=${maType}, length=${maLength}, rsiDataPoints=${rsiDataset.data.length}`);
                                }
                            }
                        }
                    }
                    
                    if (datasets.length === 0) return;
                    
                    // Log dataset info for debugging
                    console.log(`RSI chart datasets for ${selectedTimeframe}:`, datasets.map(d => ({label: d.label, isMA: d.isMA || false, dataPoints: d.data ? d.data.length : 0})));
                    
                    // Preserve current zoom level if RSI chart exists
                    let preservedMin = 0;
                    let preservedMax = allCandlestickData.length - 1;
                    const isInitialRSILoad = !rsiChart;
                    
                    // Get current x-axis range from main chart - sync with main chart
                    if (marketChart && marketChart.scales && marketChart.scales.x) {
                        // Use actual scale values from main chart (preserve zoom)
                        preservedMin = marketChart.scales.x.min;
                        preservedMax = marketChart.scales.x.max;
                    }
                    
                    // If RSI chart already exists, update it instead of recreating (preserves zoom and sync)
                    if (rsiChart && !isInitialRSILoad) {
                        // Update chart datasets
                        rsiChart.data.datasets = datasets;
                        // Preserve zoom level from main chart
                        rsiChart.options.scales.x.min = preservedMin;
                        rsiChart.options.scales.x.max = preservedMax;
                        // Update the chart (preserves zoom)
                        rsiChart.update('none');
                        return; // Exit early, chart is updated
                    }
                    
                    // Destroy existing RSI chart if it exists (should only happen on initial load)
                    if (rsiChart) {
                        rsiChart.destroy();
                    }
                    
                    // Ensure RSI levels plugin is registered before creating chart
                    ensureRSIPluginRegistered();
                    
                    // Create RSI chart (only on initial load)
                    rsiChart = new Chart(rsiChartCtx, {
                        type: 'line',
                        data: {
                            datasets: datasets
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            layout: {
                                padding: 0  // No padding to ensure exact alignment
                            },
                            interaction: {
                                intersect: false,
                                mode: 'index'
                            },
                            animation: false,  // Disable animation for instant sync
                            plugins: {
                                // rsiLevels plugin is registered globally, so it's automatically available
                                legend: {
                                    display: true,
                                    labels: {
                                        color: '#e0e0e0',
                                        font: {
                                            size: 10
                                        }
                                    }
                                },
                                tooltip: {
                                    enabled: true,
                                    callbacks: {
                                        title: function(context) {
                                            // Show timestamp for alignment with candlestick chart
                                            const point = context[0];
                                            if (point && point.raw && point.raw.t) {
                                                return point.raw.t.toLocaleString();
                                            }
                                            // Fallback: use index to get timestamp from candlestick data
                                            const dataIndex = context[0].parsed.x;
                                            if (dataIndex >= 0 && dataIndex < allCandlestickData.length) {
                                                return allCandlestickData[dataIndex].t.toLocaleString();
                                            }
                                            return 'Bar ' + dataIndex;
                                        },
                                        label: function(context) {
                                            return context.dataset.label + ': ' + context.parsed.y.toFixed(2);
                                        }
                                    }
                                },
                                zoom: {
                                    pan: {
                                        enabled: false  // Disable pan - sync with main chart instead
                                    },
                                    zoom: {
                                        wheel: {
                                            enabled: false  // Disable zoom - sync with main chart instead
                                        }
                                    }
                                }
                            },
                            scales: {
                                x: {
                                    type: 'linear',
                                    position: 'bottom',
                                    ticks: {
                                        color: '#b0b0b0',
                                        font: {
                                            size: 9
                                        },
                                        display: false  // Hide x-axis labels on RSI chart (they're on main chart)
                                    },
                                    grid: {
                                        color: '#333',
                                        display: false  // Hide grid on RSI chart
                                    },
                                    min: preservedMin,
                                    max: preservedMax,
                                    // Ensure exact alignment with candlestick chart
                                    offset: false,  // Don't add padding that could cause misalignment
                                    afterUpdate: function(scale) {
                                        // Ensure RSI chart stays synced even if scales change
                                        if (marketChart && marketChart.scales && marketChart.scales.x) {
                                            scale.min = marketChart.scales.x.min;
                                            scale.max = marketChart.scales.x.max;
                                        }
                                    }
                                },
                                y: {
                                    ticks: {
                                        color: '#2196F3',
                                        font: {
                                            size: 9
                                        },
                                        stepSize: 10
                                    },
                                    grid: {
                                        color: '#333'
                                    },
                                    title: {
                                        display: true,
                                        text: 'RSI',
                                        color: '#2196F3',
                                        font: {
                                            size: 11
                                        }
                                    },
                                    min: 0,
                                    max: 100
                                }
                            }
                        }
                    });
                    
                } catch (error) {
                    console.error('Error loading RSI chart:', error);
                }
            }
            
            // Sync RSI chart x-axis with main chart
            function syncRSIChart() {
                if (rsiChart && marketChart && marketChart.scales && marketChart.scales.x) {
                    const xMin = marketChart.scales.x.min;
                    const xMax = marketChart.scales.x.max;
                    // Get exact scale configuration from main chart for perfect alignment
                    const mainXScale = marketChart.scales.x;
                    rsiChart.options.scales.x.min = xMin;
                    rsiChart.options.scales.x.max = xMax;
                    // Ensure the RSI chart uses the exact same scale configuration
                    rsiChart.options.scales.x.offset = false;  // Match candlestick chart
                    rsiChart.update('none');
                }
            }
            
            // Listen for chart updates to sync
            function setupChartSync() {
                if (marketChart) {
                    // Override update method to sync after updates
                    const originalUpdate = marketChart.update.bind(marketChart);
                    marketChart.update = function(mode) {
                        const result = originalUpdate(mode);
                        syncRSIChart();
                        return result;
                    };
                }
            }
            
            // Zoom control functions (make them global)
            window.resetZoom = function() {
                if (marketChart && allCandlestickData.length > 0) {
                    // Reset to show all data
                    marketChart.options.scales.x.min = 0;
                    marketChart.options.scales.x.max = allCandlestickData.length - 1;
                    marketChart.update('none');
                    syncRSIChart();
                }
            };
            
            window.zoomIn = function() {
                if (marketChart && marketChart.scales && marketChart.scales.x && allCandlestickData.length > 0) {
                    const currentMin = marketChart.scales.x.min;
                    const currentMax = marketChart.scales.x.max;
                    const range = currentMax - currentMin;
                    const center = (currentMin + currentMax) / 2;
                    const newRange = range * 0.75; // Zoom in by 25%
                    const newMin = Math.max(0, center - newRange / 2);
                    const newMax = Math.min(allCandlestickData.length - 1, center + newRange / 2);
                    marketChart.options.scales.x.min = newMin;
                    marketChart.options.scales.x.max = newMax;
                    marketChart.update('none');
                    syncRSIChart();
                }
            };
            
            window.zoomOut = function() {
                if (marketChart && marketChart.scales && marketChart.scales.x && allCandlestickData.length > 0) {
                    const currentMin = marketChart.scales.x.min;
                    const currentMax = marketChart.scales.x.max;
                    const range = currentMax - currentMin;
                    const center = (currentMin + currentMax) / 2;
                    const newRange = range * 1.33; // Zoom out by 33%
                    const newMin = Math.max(0, center - newRange / 2);
                    const newMax = Math.min(allCandlestickData.length - 1, center + newRange / 2);
                    marketChart.options.scales.x.min = newMin;
                    marketChart.options.scales.x.max = newMax;
                    marketChart.update('none');
                    syncRSIChart();
                }
            };
            
            // Setup controls event listeners
            function setupControls() {
                // Timeframe selector
                const timeframeSelector = document.getElementById('timeframeSelector');
                if (timeframeSelector) {
                    // Load available timeframes and populate selector
                    fetch('/api/timeframes')
                        .then(response => response.json())
                        .then(data => {
                            availableTimeframes = data.timeframes || ['1min', '5min', '30min'];
                            timeframeSelector.innerHTML = '';
                            availableTimeframes.forEach(tf => {
                                const option = document.createElement('option');
                                option.value = tf;
                                option.textContent = tf;
                                if (tf === selectedTimeframe) {
                                    option.selected = true;
                                }
                                timeframeSelector.appendChild(option);
                            });
                        })
                        .catch(error => {
                            console.error('Error loading timeframes:', error);
                        });
                    
                    timeframeSelector.addEventListener('change', function() {
                        selectedTimeframe = this.value;
                        loadCandlestickChart(); // Reload charts with new timeframe
                    });
                }
                
                // MA toggle - save and reload chart
                const showMAToggle = document.getElementById('showMAToggle');
                if (showMAToggle) {
                    showMAToggle.addEventListener('change', async () => {
                        try {
                            const result = await fetch('/api/config/show-rsi-ma', {
                                method: 'POST',
                                headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify({value: showMAToggle.checked})
                            });
                            const data = await result.json();
                            if (data.success && rsiChart) {
                                loadRSIChart(); // Reload to update MA display
                            }
                        } catch (error) {
                            console.error('Error setting show RSI MA:', error);
                        }
                    });
                }
                
                // MA type - save and reload chart
                const maTypeEl = document.getElementById('rsiMAType');
                if (maTypeEl) {
                    maTypeEl.addEventListener('change', async () => {
                        try {
                            const result = await fetch('/api/config/rsi-ma-type', {
                                method: 'POST',
                                headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify({value: maTypeEl.value})
                            });
                            const data = await result.json();
                            if (data.success && rsiChart) {
                                loadRSIChart(); // Reload to recalculate MAs
                            }
                        } catch (error) {
                            console.error('Error setting RSI MA type:', error);
                        }
                    });
                }
                
                // MA length - save and reload chart
                const maLengthEl = document.getElementById('rsiMALength');
                if (maLengthEl) {
                    maLengthEl.addEventListener('change', async () => {
                        try {
                            const result = await fetch('/api/config/rsi-ma-length', {
                                method: 'POST',
                                headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify({value: parseInt(maLengthEl.value)})
                            });
                            const data = await result.json();
                            if (data.success && rsiChart) {
                                loadRSIChart(); // Reload to recalculate MAs
                            }
                        } catch (error) {
                            console.error('Error setting RSI MA length:', error);
                        }
                    });
                }
                
                // Divergence toggle - save and update chart
                const divergenceToggle = document.getElementById('divergenceToggle');
                if (divergenceToggle) {
                    divergenceToggle.addEventListener('change', async () => {
                        try {
                            const result = await fetch('/api/config/show-divergence', {
                                method: 'POST',
                                headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify({value: divergenceToggle.checked})
                            });
                            const data = await result.json();
                            if (data.success && rsiChart) {
                                rsiChart.update('none'); // Just update to redraw divergence
                            }
                        } catch (error) {
                            console.error('Error setting show divergence:', error);
                        }
                    });
                }
            }
            
            // Poll for new bars data every 5 seconds (adjust based on polling interval)
            // Note: loadCandlestickChart will call loadRSIChart when needed
            setInterval(() => {
                loadCandlestickChart();
            }, 5000);
            // Initial chart load after ensuring Chart.js is loaded
            setTimeout(() => {
                if (typeof Chart !== 'undefined') {
                    ensureRSIPluginRegistered();
                    setupControls(); // Setup controls first
                    loadCandlestickChart(); // Load charts
                } else {
                    console.error('Chart.js failed to load');
                }
            }, 100);
            
            // Load current config on page load
            async function loadConfig() {
                try {
                    const response = await fetch('/api/config');
                    const config = await response.json();
                    updateButtonStates(config);
                } catch (error) {
                    console.error('Error loading config:', error);
                }
            }
            
            function updateButtonStates(config) {
                const bypassStatus = document.getElementById('bypassStatus');
                const mockStatus = document.getElementById('mockStatus');
                const bypassBtn = document.getElementById('bypassBtn');
                const mockBtn = document.getElementById('mockBtn');
                const pollingIntervalInput = document.getElementById('pollingInterval');
                
                // When bypass_market_hours is True, we respect market hours (Trade 24/7 OFF)
                // When bypass_market_hours is False, we ignore market hours (Trade 24/7 ON)
                if (config.bypass_market_hours) {
                    bypassStatus.textContent = 'OFF';  // Trade 24/7 is OFF (respecting market hours)
                    bypassBtn.style.borderColor = '#666';
                    bypassBtn.style.background = '#444';
                } else {
                    bypassStatus.textContent = 'ON';  // Trade 24/7 is ON (ignoring market hours)
                    bypassBtn.style.borderColor = '#4CAF50';
                    bypassBtn.style.background = '#2d4a2d';
                }
                
                if (config.use_mock_data) {
                    mockStatus.textContent = 'ON';
                    mockBtn.style.borderColor = '#FF9800';
                    mockBtn.style.background = '#4a3a2d';
                } else {
                    mockStatus.textContent = 'OFF';
                    mockBtn.style.borderColor = '#666';
                    mockBtn.style.background = '#444';
                }
                
                // Update polling interval input - always show a value (default to 30 if not set)
                const pollingValue = config.polling_interval_seconds !== null && config.polling_interval_seconds !== undefined 
                    ? config.polling_interval_seconds 
                    : 30;
                pollingIntervalInput.value = pollingValue;
                
                // Update historical bars count input
                const historicalBarsInput = document.getElementById('historicalBarsCount');
                if (historicalBarsInput) {
                    const barsValue = config.historical_bars_count !== null && config.historical_bars_count !== undefined 
                        ? config.historical_bars_count 
                        : 2000;
                    historicalBarsInput.value = barsValue;
                }
                
                // Update RSI MA settings
                const rsiMATypeSelect = document.getElementById('rsiMAType');
                if (rsiMATypeSelect) {
                    const maType = config.rsi_ma_type !== null && config.rsi_ma_type !== undefined 
                        ? config.rsi_ma_type 
                        : 'None';
                    rsiMATypeSelect.value = maType;
                }
                
                const rsiMALengthInput = document.getElementById('rsiMALength');
                if (rsiMALengthInput) {
                    const maLength = config.rsi_ma_length !== null && config.rsi_ma_length !== undefined 
                        ? config.rsi_ma_length 
                        : 14;
                    rsiMALengthInput.value = maLength;
                }
                
                const showMAToggle = document.getElementById('showMAToggle');
                if (showMAToggle) {
                    showMAToggle.checked = config.show_rsi_ma === true;
                }
                
                const divergenceToggle = document.getElementById('divergenceToggle');
                if (divergenceToggle) {
                    divergenceToggle.checked = config.show_divergence === true;
                }
            }
            
            async function toggleBypassMarketHours() {
                try {
                    const response = await fetch('/api/config');
                    const config = await response.json();
                    const newValue = !config.bypass_market_hours;
                    
                    const result = await fetch('/api/config/bypass-market-hours', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({value: newValue})
                    });
                    const data = await result.json();
                    updateButtonStates(data);
                } catch (error) {
                    console.error('Error toggling bypass market hours:', error);
                }
            }
            
            async function toggleMockData() {
                try {
                    const response = await fetch('/api/config');
                    const config = await response.json();
                    const newValue = !config.use_mock_data;
                    
                    const result = await fetch('/api/config/mock-data', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({value: newValue})
                    });
                    const data = await result.json();
                    updateButtonStates(data);
                    // Mock data will take effect on next polling cycle (no restart needed)
                } catch (error) {
                    console.error('Error toggling mock data:', error);
                }
            }
            
            async function setPollingInterval() {
                const input = document.getElementById('pollingInterval');
                const value = parseInt(input.value);
                
                if (isNaN(value) || value < 1) {
                    alert('Please enter a valid polling interval (minimum 1 second)');
                    return;
                }
                
                try {
                    const result = await fetch('/api/config/polling-interval', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({value: value})
                    });
                    const data = await result.json();
                    
                    if (data.success) {
                        updateButtonStates(data);
                        alert(`Polling interval set to ${value} seconds. Changes take effect on the next polling cycle.`);
                    } else {
                        alert('Error setting polling interval: ' + data.message);
                    }
                } catch (error) {
                    console.error('Error setting polling interval:', error);
                    alert('Error setting polling interval. Please try again.');
                }
            }
            
            // Make setPollingInterval available globally
            window.setPollingInterval = setPollingInterval;
            
            async function setHistoricalBarsCount() {
                const input = document.getElementById('historicalBarsCount');
                const value = parseInt(input.value);
                
                if (isNaN(value) || value < 100) {
                    alert('Please enter a valid historical bars count (minimum 100)');
                    return;
                }
                
                try {
                    const result = await fetch('/api/config/historical-bars-count', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({value: value})
                    });
                    const data = await result.json();
                    
                    if (data.success) {
                        updateButtonStates(data);
                        alert(`Historical bars count set to ${value}. Changes take effect on the next data fetch cycle.`);
                    } else {
                        alert('Error setting historical bars count: ' + data.message);
                    }
                } catch (error) {
                    console.error('Error setting historical bars count:', error);
                    alert('Error setting historical bars count. Please try again.');
                }
            }
            
            // Make setHistoricalBarsCount available globally
            window.setHistoricalBarsCount = setHistoricalBarsCount;
            
            // Load config on page load
            loadConfig();
            
            // Load existing alerts on page load
            async function loadAlerts() {
                try {
                    const response = await fetch('/api/alerts');
                    const data = await response.json();
                    if (data.alerts && data.alerts.length > 0) {
                        // Load alerts in reverse order (oldest first) so newest appear at top when inserted
                        for (let i = data.alerts.length - 1; i >= 0; i--) {
                            addAlert(data.alerts[i]);
                        }
                        console.log(`Loaded ${data.alerts.length} existing alerts from storage`);
                    }
                } catch (error) {
                    console.error('Error loading alerts:', error);
                }
            }
            
            // Load alerts when page loads (WebSocket will also send recent alerts on connect)
            loadAlerts();
            
            // Function to clear all alerts
            async function clearAlerts() {
                if (!confirm('Are you sure you want to clear all alerts? This cannot be undone.')) {
                    return;
                }
                
                try {
                    const response = await fetch('/api/alerts', {
                        method: 'DELETE'
                    });
                    const data = await response.json();
                    
                    if (data.success) {
                        // Clear the displayed alerts
                        alertsDiv.innerHTML = '';
                        console.log('All alerts cleared');
                    } else {
                        alert('Error clearing alerts: ' + data.message);
                    }
                } catch (error) {
                    console.error('Error clearing alerts:', error);
                    alert('Error clearing alerts. Please try again.');
                }
            }
            
            // Make clearAlerts available globally
            window.clearAlerts = clearAlerts;
            
            function addAlert(alert) {
                // Prevent duplicate alerts (check if alert with same timestamp already exists)
                const existingAlerts = Array.from(alertsDiv.children);
                const isDuplicate = existingAlerts.some(existing => {
                    const existingTimestamp = existing.querySelector('.alert-details')?.textContent;
                    const newTimestamp = new Date(alert.timestamp).toLocaleString();
                    return existingTimestamp && existingTimestamp.includes(newTimestamp.split(',')[1]?.trim() || '');
                });
                if (isDuplicate) {
                    console.log('Skipping duplicate alert:', alert);
                    return;
                }
                
                const alertDiv = document.createElement('div');
                alertDiv.className = `alert ${alert.signal_type}`;
                
                const timestamp = new Date(alert.timestamp).toLocaleString();
                // Get first line of message (handle both \n and actual newlines)
                const messageFirstLine = (alert.message || '').split('\n')[0].split('\\n')[0] || alert.signal_type.toUpperCase();
                
                alertDiv.innerHTML = `
                    <div class="alert-header">${messageFirstLine}</div>
                    <div class="rsi-value">RSI: ${alert.rsi_value.toFixed(2)}</div>
                    <div class="alert-details">
                        Timeframe: ${alert.timeframe} | 
                        Confirmed: ${alert.confirmed ? '✅' : '❌'} | 
                        ${timestamp}
                    </div>
                `;
                
                alertsDiv.insertBefore(alertDiv, alertsDiv.firstChild);
                
                // Keep only last 50 alerts visible
                while (alertsDiv.children.length > 50) {
                    alertsDiv.removeChild(alertsDiv.lastChild);
                }
            }
        </script>
    </body>
    </html>
    """
    return html


@app.get("/api/alerts")
async def get_alerts():
    """Get recent alerts."""
    return {"alerts": recent_alerts, "count": len(recent_alerts)}


@app.delete("/api/alerts")
async def clear_alerts():
    """Clear all alerts from memory and persistent storage."""
    global recent_alerts
    try:
        # Clear persistent storage
        alert_storage.clear()
        # Clear in-memory cache
        recent_alerts = []
        print("All alerts cleared")
        return {"success": True, "message": "All alerts cleared", "count": 0}
    except Exception as e:
        print(f"Error clearing alerts: {e}")
        return {"success": False, "message": str(e), "count": len(recent_alerts)}


@app.get("/api/market-data")
async def get_market_data():
    """Get latest market data (price and RSI) for charting."""
    return latest_market_data


@app.get("/api/rsi-history")
async def get_rsi_history():
    """Get RSI history for all timeframes."""
    # Return RSI data for charting
    return {
        "rsi_1min": getattr(runtime_config, 'rsi_history_1min', []),
        "rsi_5min": getattr(runtime_config, 'rsi_history_5min', []),
        "rsi_30min": getattr(runtime_config, 'rsi_history_30min', [])
    }


@app.get("/api/bars/{timeframe}")
async def get_bars(timeframe: str):
    """Get historical bars for a timeframe."""
    bars = historical_bars.get(timeframe, [])
    return {"bars": bars, "count": len(bars), "timeframe": timeframe}


@app.get("/api/timeframes")
async def get_timeframes():
    """Get available timeframes from config."""
    config = AppConfig.from_env()
    return {"timeframes": config.timeframes.timeframes}


@app.get("/api/config")
async def get_config():
    """Get runtime configuration."""
    return runtime_config.get_config()


@app.post("/api/config/bypass-market-hours")
async def toggle_bypass_market_hours(request: Request):
    """Toggle bypass market hours setting."""
    data = await request.json()
    value = data.get("value", False)
    runtime_config.set_bypass_market_hours(value)
    return runtime_config.get_config()


@app.post("/api/config/mock-data")
async def toggle_mock_data(request: Request):
    """Toggle mock data (simulate mode)."""
    data = await request.json()
    value = data.get("value", False)
    runtime_config.set_use_mock_data(value)
    return runtime_config.get_config()


@app.post("/api/config/polling-interval")
async def set_polling_interval(request: Request):
    """Set polling interval in seconds."""
    data = await request.json()
    value = data.get("value")
    if value is None:
        return {"success": False, "message": "Value is required"}
    try:
        interval = int(value)
        runtime_config.set_polling_interval(interval)
        return {"success": True, **runtime_config.get_config()}
    except ValueError as e:
        return {"success": False, "message": str(e)}


@app.post("/api/config/historical-bars-count")
async def set_historical_bars_count(request: Request):
    """Set historical bars count."""
    data = await request.json()
    value = data.get("value")
    if value is None:
        return {"success": False, "message": "Value is required"}
    try:
        count = int(value)
        runtime_config.set_historical_bars_count(count)
        return {"success": True, **runtime_config.get_config()}
    except ValueError as e:
        return {"success": False, "message": str(e)}


@app.post("/api/config/rsi-ma-type")
async def set_rsi_ma_type(request: Request):
    """Set RSI MA type."""
    data = await request.json()
    value = data.get("value")
    if value is None:
        return {"success": False, "message": "Value is required"}
    try:
        runtime_config.set_rsi_ma_type(value)
        return {"success": True, **runtime_config.get_config()}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.post("/api/config/rsi-ma-length")
async def set_rsi_ma_length(request: Request):
    """Set RSI MA length."""
    data = await request.json()
    value = data.get("value")
    if value is None:
        return {"success": False, "message": "Value is required"}
    try:
        length = int(value)
        runtime_config.set_rsi_ma_length(length)
        return {"success": True, **runtime_config.get_config()}
    except ValueError as e:
        return {"success": False, "message": str(e)}


@app.post("/api/config/show-rsi-ma")
async def set_show_rsi_ma(request: Request):
    """Set show RSI MA flag."""
    data = await request.json()
    value = data.get("value")
    if value is None:
        return {"success": False, "message": "Value is required"}
    try:
        runtime_config.set_show_rsi_ma(bool(value))
        return {"success": True, **runtime_config.get_config()}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.post("/api/config/show-divergence")
async def set_show_divergence(request: Request):
    """Set show divergence flag."""
    data = await request.json()
    value = data.get("value")
    if value is None:
        return {"success": False, "message": "Value is required"}
    try:
        runtime_config.set_show_divergence(bool(value))
        return {"success": True, **runtime_config.get_config()}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time alerts."""
    global _loop
    # Capture event loop on first WebSocket connection
    if _loop is None:
        _loop = asyncio.get_event_loop()
    
    await websocket.accept()
    active_connections.append(websocket)
    
    # Send recent alerts to new connection (already in newest-first order)
    # Send them in reverse order so they display correctly when inserted at top
    for alert in reversed(recent_alerts[:20]):
        try:
            await websocket.send_json(alert)
        except:
            break
    
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.remove(websocket)


def broadcast_alert(signal: Signal, message: str):
    """Broadcast alert to API (to be called from main app)."""
    global _loop
    if _loop is None:
        try:
            _loop = asyncio.get_event_loop()
        except RuntimeError:
            # No event loop in this thread, create a new one
            asyncio.run(add_alert(signal, message))
            return
    
    # Schedule the coroutine on the event loop
    if _loop.is_running():
        asyncio.run_coroutine_threadsafe(add_alert(signal, message), _loop)
    else:
        _loop.run_until_complete(add_alert(signal, message))


def update_market_data(timestamp: datetime, price: float, rsi_by_timeframe: dict):
    """
    Update latest market data for charting.
    
    Args:
        timestamp: Current timestamp
        price: Current price
        rsi_by_timeframe: Dict mapping timeframe to RSI value
    """
    global latest_market_data
    latest_market_data = {
        "timestamp": timestamp.isoformat(),
        "price": price,
        "rsi": rsi_by_timeframe
    }


def update_historical_bars(timeframe: str, bars: List[Bar]):
    """
    Update historical bars for a timeframe (for candlestick chart).
    
    Args:
        timeframe: Timeframe string (e.g., "1min", "5min", "30min")
        bars: List of Bar objects for the timeframe
    """
    global historical_bars
    # Convert bars to dict format for JSON serialization
    historical_bars[timeframe] = [
        {
            "timestamp": bar.timestamp.isoformat(),
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume
        }
        for bar in bars
    ]



