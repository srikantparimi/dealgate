# Backlog

One markdown file per story. File name: `s{sprint}-e{epic}-{slug}.md`.

Template — copy for every new story:

```markdown
# Sn Ex — <verb + noun in the user's language>

## User story
As a <role>, I <do X> so that <outcome>.

## Acceptance tests (Given/When/Then)
- Given …, when …, then ….
- Given …, when …, then ….

## Data touched
- Tables: …
- Immutable versions written: …
- Audit events emitted: `<event.name>` with `{…}`

## Roles allowed
- <role>: <endpoints / pages>

## Out of scope
- …

## Notes
- Links to blueprint § and build-guide §.
```

Rules for the lead when breaking down a sprint:

- Every story is a vertical slice (migration + API + page + tests).
- ≤ ~400 changed lines per PR.
- If a story cannot be sliced under 400 lines, split it — never merge two.
- No story ships without a page a human can click through on staging.
