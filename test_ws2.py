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
            
            payload = json.dumps({"type": "input", "payload": "run security audit"})
            print(f"Sending: {payload}")
            await ws.send(payload)
            
            resp = await ws.recv()
            print("Received:", resp)
            
            try:
                # wait to see if we get the executor output
                for i in range(5):
                    output = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    print(f"Output {i}:", output)
            except asyncio.TimeoutError:
                print("Timed out waiting for more execution.")
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(test())
