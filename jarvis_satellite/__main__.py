"""Entry point for running jarvis_satellite as a module."""

import asyncio
from .main import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

