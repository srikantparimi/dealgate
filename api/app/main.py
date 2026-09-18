from fastapi import FastAPI

from app.routers import (
    actuals,
    admin_policy,
    admin_rate_cards,
    admin_replay,
    admin_users,
    adviser,
    agreements,
    approvals,
    audit,
    ceo_exception,
    clients,
    dashboards,
    deals,
    delivery_model,
    forecast,
    gm,
    health,
    hubspot,
    legacy,
    me,
    notifications,
    renewals,
    signed_sow,
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
app.include_router(approvals.router)
app.include_router(ceo_exception.router)
app.include_router(signed_sow.router)
app.include_router(renewals.router)
app.include_router(dashboards.router)
app.include_router(forecast.router)
app.include_router(actuals.router)
app.include_router(admin_replay.router)
