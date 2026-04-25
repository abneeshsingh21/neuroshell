# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
import webview
import threading
import uvicorn
import time
import requests
import sys
import os

from server import app

# Ensure working directory is correct so static files resolve
os.chdir(os.path.dirname(os.path.abspath(__file__)))

def start_server():
    """Run FastAPI server in a separate thread."""
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error")

if __name__ == '__main__':
    # Start the backend server on port 8000
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    
    # Simple wait mechanism until server is accepting connections
    server_ready = False
    for i in range(20):
        try:
            resp = requests.get("http://127.0.0.1:8000/", timeout=1)
            if resp.status_code == 200:
                server_ready = True
                break
        except Exception:
            time.sleep(0.5)
            
    if not server_ready:
        print("Failed to start or connect to the internal AI backend engine.", file=sys.stderr)
        sys.exit(1)

    # Launch PyWebView Native Window
    window = webview.create_window(
        title="NeuroShell Terminal \u2014 Pro Edition", 
        url="http://127.0.0.1:8000/",
        width=1280,
        height=800,
        min_size=(900, 600),
        background_color="#09090b",
        frameless=False,
    )
    
    # Start the native OS loop
    webview.start(debug=False)
