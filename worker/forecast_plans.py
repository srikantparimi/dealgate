"""Run the tenant-scoped transactional Forecast calculation queue once."""

import asyncio
import json

from app.db import session_factory
from app.services.forecast_plans import process_plan_jobs


async def main():
    async with session_factory() as session:
        handled = await process_plan_jobs(session)
        print(json.dumps({"worker": "forecast_plans", "handled": handled}))


if __name__ == "__main__":
    asyncio.run(main())
