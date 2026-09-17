"""State machine and role checks. Every state change goes through here and
writes an audit_event in the same transaction. Sprint 1 implements Intake →
Coverage → SOWDraft. See docs/build-guide.md §4.
"""
