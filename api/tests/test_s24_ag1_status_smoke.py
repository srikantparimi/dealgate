"""S24-AG1 B2 smoke: the shared loader runs on the PL2 seed within the statement budget."""

import uuid

from sqlalchemy import event

from app.auth import AuthUser
from app.services.agreement_status import KINDS, cards, load_agreement_population, matches, workspace_payload
from tests.test_s23_pl2_workspace import engine, frozen_clock, seeded  # noqa: F401  (fixtures)

ADMIN = AuthUser(uuid.UUID("00000000-0000-4000-8000-0000000000a1"), "admin@example.test", "Ada Admin", ("SystemAdmin",))


async def test_loader_classifies_every_visible_client_within_budget(engine, session, seeded):  # noqa: F811
    statements: list[str] = []

    def count(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        if not statement.lstrip().upper().startswith(("SAVEPOINT", "RELEASE")):
            statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", count)
    try:
        pop = await load_agreement_population(session, ADMIN, with_activity=True)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count)
    payload = workspace_payload(pop, {}, page=1, page_size=25, can_write=True, is_admin=True)
    assert payload["total"] == len(pop.clients) > 0
    assert len(payload["cards"]) == 6
    for card in cards(pop.statuses):
        assert sum(1 for s in pop.statuses if matches(s, card["drill"])) == card["value"], card["key"]
    for row in payload["items"]:
        assert row["nda"]["state"] in ("client", "standard", "covered", "missing", "due_later", "not_needed",
                                       "existing_none")
    print("statements", len(statements), "clients", len(pop.clients),
          {c["key"]: c["value"] for c in payload["cards"]},
          sorted({(f.status.relationship, f.status.requirement, f.status.nda, f.status.msa) for f in pop.clients.values()}))
    assert len(statements) <= 8
    assert set(KINDS) == {"NDA", "MSA"}
