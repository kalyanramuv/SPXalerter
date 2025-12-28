"""FastAPI dashboard for RSI alerts."""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi import Request
from typing import List
from datetime import datetime
from signals.detector import Signal
from alerts.storage import AlertStorage
from api.runtime_config import runtime_config
from providers.base import Bar
import json


app = FastAPI(title="RSI Live Alerter")

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

# Store historical bars for 1min timeframe (for candlestick chart)
historical_bars_1min: List[dict] = []

# Load alerts from persistent storage on startup
def _load_alerts_from_storage():
    """Load alerts from persistent storage."""
    global recent_alerts
    recent_alerts = alert_storage.load_alerts(max_alerts=MAX_ALERTS)
    print(f"Loaded {len(recent_alerts)} alerts from persistent storage")

# Initialize on module load
_load_alerts_from_storage()


def add_alert(signal: Signal, message: str):
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
            connection.send_json(alert_data)
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
            .alert.bullish_reclaim { border-left-color: #4CAF50; }
            .alert.bearish_reclaim { border-left-color: #FF9800; }
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
                        Skip Market Hours: <span id="bypassStatus">OFF</span>
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
                            <div class="chart-title">SPY 1-Minute Candlestick Chart</div>
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
                            <div class="rsi-chart-title">RSI (1min, 5min, 30min)</div>
                            <canvas id="rsiChart"></canvas>
                            <div class="rsi-controls">
                                <label>
                                    Oversold:
                                    <input type="number" id="oversoldLevel" value="30" min="0" max="100" step="1">
                                </label>
                                <label>
                                    Overbought:
                                    <input type="number" id="overboughtLevel" value="70" min="0" max="100" step="1">
                                </label>
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
            let rsiData = {
                '1min': [],
                '5min': [],
                '30min': []
            };
            
            // RSI threshold levels (configurable)
            let oversoldLevel = 30;
            let overboughtLevel = 70;
            
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
                    
                    const response = await fetch('/api/bars/1min');
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
                    let preservedMin = 0;
                    let preservedMax = newCandlestickData.length - 1;
                    const isInitialLoad = !marketChart;
                    
                    if (!isInitialLoad && marketChart && marketChart.scales && marketChart.scales.x) {
                        // Preserve current zoom level
                        preservedMin = marketChart.scales.x.min;
                        preservedMax = marketChart.scales.x.max;
                        // Ensure preserved values are within valid range for new data
                        preservedMin = Math.max(0, Math.min(preservedMin, newCandlestickData.length - 1));
                        preservedMax = Math.max(preservedMin + 1, Math.min(preservedMax, newCandlestickData.length - 1));
                    }
                    
                    // Update the global data array
                    allCandlestickData = newCandlestickData;
                    
                    // If chart already exists, update it instead of recreating (preserves zoom)
                    if (marketChart && !isInitialLoad) {
                        // Update chart data
                        marketChart.data.datasets[0].data = allCandlestickData;
                        // Update zoom limits for new data length
                        if (marketChart.options.plugins.zoom.zoom.limits) {
                            marketChart.options.plugins.zoom.zoom.limits.x.max = allCandlestickData.length - 1;
                        }
                        // Preserve zoom level by setting min/max before update
                        marketChart.options.scales.x.min = preservedMin;
                        marketChart.options.scales.x.max = preservedMax;
                        // Update the chart (this preserves the zoom)
                        marketChart.update('none');
                        // Reload RSI chart to sync with updated data
                        loadRSIChart();
                        return; // Exit early, chart is updated
                    }
                    
                    // Destroy existing chart if it exists (should only happen on initial load or errors)
                    if (marketChart) {
                        marketChart.destroy();
                    }
                    
                    // Create new candlestick chart (only on initial load)
                    marketChart = new Chart(chartCtx, {
                        type: 'candlestick',
                        data: {
                            datasets: [{
                                label: 'SPY 1min',
                                data: allCandlestickData
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
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
                    
                    if (!data || (!data.rsi_1min || data.rsi_1min.length === 0) && 
                        (!data.rsi_5min || data.rsi_5min.length === 0) && 
                        (!data.rsi_30min || data.rsi_30min.length === 0)) {
                        console.log('No RSI data available yet');
                        return;
                    }
                    
                    // Create RSI chart data - align with main chart indices
                    const datasets = [];
                    
                    if (data.rsi_1min && data.rsi_1min.length > 0) {
                        datasets.push({
                            label: 'RSI 1min',
                            data: data.rsi_1min.map(point => ({ x: point.index, y: point.rsi })),
                            borderColor: '#2196F3',
                            backgroundColor: 'rgba(33, 150, 243, 0.1)',
                            tension: 0.1,
                            fill: false,
                            pointRadius: 0
                        });
                    }
                    
                    if (data.rsi_5min && data.rsi_5min.length > 0) {
                        datasets.push({
                            label: 'RSI 5min',
                            data: data.rsi_5min.map(point => ({ x: point.index, y: point.rsi })),
                            borderColor: '#FF9800',
                            backgroundColor: 'rgba(255, 152, 0, 0.1)',
                            tension: 0.1,
                            fill: false,
                            pointRadius: 0
                        });
                    }
                    
                    if (data.rsi_30min && data.rsi_30min.length > 0) {
                        datasets.push({
                            label: 'RSI 30min',
                            data: data.rsi_30min.map(point => ({ x: point.index, y: point.rsi })),
                            borderColor: '#9C27B0',
                            backgroundColor: 'rgba(156, 39, 176, 0.1)',
                            tension: 0.1,
                            fill: false,
                            pointRadius: 0
                        });
                    }
                    
                    if (datasets.length === 0) return;
                    
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
                    rsiChart.options.scales.x.min = xMin;
                    rsiChart.options.scales.x.max = xMax;
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
            
            // Poll for new bars data every 5 seconds (adjust based on polling interval)
            // Note: loadCandlestickChart will call loadRSIChart when needed
            setInterval(() => {
                loadCandlestickChart();
            }, 5000);
            // Initial chart load after ensuring Chart.js is loaded
            setTimeout(() => {
                if (typeof Chart !== 'undefined') {
                    ensureRSIPluginRegistered();
                    loadCandlestickChart();
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
                
                if (config.bypass_market_hours) {
                    bypassStatus.textContent = 'ON';
                    bypassBtn.style.borderColor = '#4CAF50';
                    bypassBtn.style.background = '#2d4a2d';
                } else {
                    bypassStatus.textContent = 'OFF';
                    bypassBtn.style.borderColor = '#666';
                    bypassBtn.style.background = '#444';
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
                const alertDiv = document.createElement('div');
                alertDiv.className = `alert ${alert.signal_type}`;
                
                const timestamp = new Date(alert.timestamp).toLocaleString();
                alertDiv.innerHTML = `
                    <div class="alert-header">${alert.message.split('\\n')[0]}</div>
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


@app.get("/api/bars/1min")
async def get_bars_1min():
    """Get historical 1-minute bars for candlestick chart."""
    return {"bars": historical_bars_1min, "count": len(historical_bars_1min)}


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


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time alerts."""
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
    add_alert(signal, message)


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


def update_historical_bars_1min(bars: List[Bar]):
    """
    Update historical bars for 1min timeframe (for candlestick chart).
    
    Args:
        bars: List of Bar objects for 1min timeframe
    """
    global historical_bars_1min
    # Convert bars to dict format for JSON serialization
    historical_bars_1min = [
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



