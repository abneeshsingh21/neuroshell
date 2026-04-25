# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
import asyncio
import websockets
import json

async def test():
    try:
        async with websockets.connect("ws://localhost:8000/ws/terminal") as ws:
            print("Connected.")
            welcome = await ws.recv()
            print("Received:", welcome)
            
            payload = json.dumps({"type": "input", "payload": "echo HELLO"})
            print(f"Sending: {payload}")
            await ws.send(payload)
            
            resp = await ws.recv()
            print("Received:", resp)
            
            # Wait for execution response
            resp2 = await ws.recv()
            print("Received:", resp2)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(test())
