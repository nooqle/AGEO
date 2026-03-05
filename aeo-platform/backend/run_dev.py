"""Development server launcher.

Uses loop="none" to prevent uvicorn from overriding Windows default
ProactorEventLoop with SelectorEventLoop (which breaks Patchright).

Usage:
    python run_dev.py
"""
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:socket_app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        loop="none",
    )
