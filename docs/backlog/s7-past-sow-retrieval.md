# S7 — Past-SOW retrieval + capability catalog (pgvector)

## User story
As the adviser, when I propose a team for a new opportunity, I search past
approved SOWs and the capability catalog to ground the proposal in what
DealGate has actually done. Boosts confidence, reduces made-up roles.

## Acceptance
- `pgvector` extension enabled on RDS (migration, Postgres-only).
- New table `sow_embedding` (sow_version_id FK, chunk_index, chunk_text
  TEXT, embedding VECTOR(1536), created_at). One row per ~500-char chunk
  of the confirmed SOW extracted_fields' scope + deliverables.
- New table `capability_catalog` (id, name, description, tags text[],
  embedding VECTOR(1536), curated_by, created_at, updated_at) — Delivery
  Lead / SystemAdmin can add / edit entries.
- Background job on `sow.confirmed` audit: chunk + embed via Bedrock
  Titan embedding v2 → `sow_embedding` rows. Idempotent per sow_version.
- Adviser service extended:
  - Before Bedrock role proposal, embed the intake `problem` and query
    `sow_embedding` for top-5 similar past SOWs (cosine).
  - Query `capability_catalog` for top-5 relevant capabilities.
  - Inject both into the LLM prompt as context.
  - Store retrieved refs in `adviser_estimate.retrieved` JSON field
    (add column via migration).
- `/admin/capability-catalog` endpoints: list, create, patch, delete
  (Delivery / SystemAdmin). PATCH re-embeds the description.
- Web: `web/src/pages/CapabilityCatalog.tsx` — table + edit modal.
- Tests: mocked Bedrock embeddings deterministic; SQLite fallback for
  the vector search (skip when Postgres unavailable — pgvector-only).

## Config
- New env: `BEDROCK_EMBEDDING_MODEL_ID` (default
  `amazon.titan-embed-text-v2:0`).

## Notes
- Blueprint §5 "Retrieve past SOWs + capability catalog", §11 pgvector.
- Vector index: HNSW on both tables (`CREATE INDEX USING hnsw`).
