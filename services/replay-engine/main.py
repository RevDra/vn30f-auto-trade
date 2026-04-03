"""Entry point for Replay Engine service."""
import uvicorn

# Re-export app for uvicorn
from app.api import app  # noqa: F401

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
