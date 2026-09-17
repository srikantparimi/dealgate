from fastapi import FastAPI

from app.routers import admin_users, audit, deals, health, hubspot, me

app = FastAPI(title="DealGate API", version="0.0.1")
app.include_router(health.router)
app.include_router(me.router)
app.include_router(hubspot.router)
app.include_router(deals.router)
app.include_router(audit.router)
app.include_router(admin_users.router)
