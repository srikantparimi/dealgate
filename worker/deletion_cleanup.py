"""Drain tenant-scoped persisted SOW object cleanup jobs."""

import asyncio
import json

from app.db import session_factory
from app.services.deletion_cleanup import process_deletion_jobs


async def main():
    async with session_factory() as session:
        handled = await process_deletion_jobs(session)
    print(json.dumps({"worker": "deletion_cleanup", "handled": handled}))


if __name__ == "__main__":
    asyncio.run(main())
