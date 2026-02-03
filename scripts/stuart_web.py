from __future__ import annotations

import os

import uvicorn

# Entrypoint: run the Stuart web door.
# Usage:
#   python scripts/stuart_web.py
# Environment:
#   STUART_ROOT=/path/to/runtime (optional; defaults to ~/ashby_runtime/stuart)

def main() -> None:
    port = int(os.environ.get("STUART_WEB_PORT", "8844"))
    uvicorn.run("ashby.interfaces.web.app:app", host="127.0.0.1", port=port, reload=False)

if __name__ == "__main__":
    main()
