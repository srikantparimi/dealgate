"""External integrations: hubspot, ses, teams, bedrock. Each module is a thin
adapter with the real client and a stub used by tests. Never call these from
inside app/gm or app/workflow directly; go through a service.
"""
