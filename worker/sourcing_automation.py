"""Process the scoped sourcing automation outbox once, without mail or hiring."""
import asyncio
import json
import os

from sqlalchemy import text

from app.db import session_factory
from app.services.automation_jobs import process_jobs


async def main():
    async with session_factory() as session:
        if session.get_bind().dialect.name == "postgresql":
            await session.execute(text("SELECT set_config('application_name', :name, false)"),
                {"name": f"sourcing_automation:{os.getpid()}"})
        handled = await process_jobs(session)
        print(json.dumps({"worker": "sourcing_automation", "handled": handled}))


if __name__ == "__main__":
    asyncio.run(main())
