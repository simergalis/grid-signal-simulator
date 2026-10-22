from __future__ import annotations

import os

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "mcp_server.server:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8099")),
        log_level="info",
    )
