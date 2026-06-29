from __future__ import annotations

import uvicorn

from .api import app
from .config import SETTINGS


if __name__ == "__main__":
    uvicorn.run(app, host=SETTINGS.app_host, port=SETTINGS.app_port)
