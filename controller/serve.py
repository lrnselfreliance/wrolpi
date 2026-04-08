"""
Entry point for the WROLPi Controller.

Starts uvicorn on port 80 (the primary HTTP entry point for users).
Docker maps this to external port 8080; native/RPi uses port 80 directly.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("controller.main:app", host="0.0.0.0", port=80, log_level="info")
