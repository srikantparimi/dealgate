# DealGate Build Guide (design)

The living copy of this document is a Claude Doc:
<https://claude.ai/code/artifact/45b6e18d-a44b-41c1-a178-2273995301e0>

That doc is the design of record. When it changes, mirror the relevant section
here so agents working from the repo have a self-contained reference.

Sections:

1. What we're building
2. Hard rules the system enforces
3. Roles and permissions
4. End-to-end workflow
5. Module 1: Opportunity Adviser
6. Module 2: Deal Governance
7. GM engine
8. Delivery model map
9. Alerts, renewals and dashboards
10. Data model
11. AWS architecture
12. Security and audit
13. Delivery plan
14. Instructions for build agents
15. Decisions to close in Sprint 0, and risks

## What lives here vs. in the Claude Doc

- **Claude Doc**: current wording, edits, comments from stakeholders.
- **This file**: the version the agents work against for the current sprint.
  Update it at the start of each sprint from the Claude Doc, then don't chase
  wording changes mid-sprint.
