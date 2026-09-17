"""Service layer: orchestration between routers, integrations, and the DB.

Services own transactions and audit emission. Routers should stay thin.
"""
