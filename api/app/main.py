from fastapi import FastAPI

from app.routers import (
    admin_policy,
    admin_rate_cards,
    admin_users,
    adviser,
    agreements,
    audit,
    clients,
    deals,
    delivery_model,
    gm,
    health,
    hubspot,
    legacy,
    me,
    notifications,
    sow,
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
app.include_router(sow.router)
app.include_router(delivery_model.router)
app.include_router(adviser.router)
app.include_router(legacy.router)
