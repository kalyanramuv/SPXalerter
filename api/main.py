"""FastAPI dashboard for RSI alerts."""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from typing import List
from datetime import datetime
from signals.detector import Signal
from alerts.storage import AlertStorage
import json


app = FastAPI(title="RSI Live Alerter")

# Persistent storage for alerts
alert_storage = AlertStorage(storage_file="alerts_history.json")
MAX_ALERTS = 100

# In-memory cache for quick access (loaded from persistent storage)
recent_alerts: List[dict] = []

# WebSocket connections
active_connections: List[WebSocket] = []

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
                max-width: 1200px;
                margin: 0 auto;
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
            .alerts {
                margin-top: 20px;
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
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📊 RSI Live Alerter - SPY</h1>
            <div id="status" class="status disconnected">Disconnected</div>
            <div class="alerts" id="alerts"></div>
        </div>
        <script>
            const ws = new WebSocket(`ws://${window.location.host}/ws`);
            const statusDiv = document.getElementById('status');
            const alertsDiv = document.getElementById('alerts');
            
            ws.onopen = () => {
                statusDiv.textContent = '✅ Connected - Listening for alerts...';
                statusDiv.className = 'status connected';
            };
            
            ws.onclose = () => {
                statusDiv.textContent = '❌ Disconnected - Reconnecting...';
                statusDiv.className = 'status disconnected';
                setTimeout(() => location.reload(), 3000);
            };
            
            ws.onmessage = (event) => {
                const alert = JSON.parse(event.data);
                addAlert(alert);
            };
            
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


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time alerts."""
    await websocket.accept()
    active_connections.append(websocket)
    
    # Send recent alerts to new connection
    for alert in recent_alerts[:20]:
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



