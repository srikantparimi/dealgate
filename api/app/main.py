from fastapi import FastAPI

from app.routers import (
    admin_policy,
    admin_rate_cards,
    admin_users,
    agreements,
    audit,
    clients,
    deals,
    gm,
    health,
    hubspot,
    me,
    notifications,
    tasks,
)

app = FastAPI(title="DealGate API", version="0.0.1")
app.include_router(health.router)
app.include_router(me.router)
app.include_router(hubspot.router)
app.include_router(deals.router)
app.include_router(audit.router)
app.include_router(admin_users.router)
app.include_router(clients.router)
app.include_router(agreements.router)
app.include_router(tasks.router)
app.include_router(notifications.router)
app.include_router(admin_rate_cards.router)
app.include_router(admin_policy.router)
app.include_router(gm.router)
