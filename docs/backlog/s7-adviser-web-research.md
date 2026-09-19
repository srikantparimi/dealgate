# S7 — Adviser: real web research (Tavily) + confidential/public split

## User story
As Marketing, when I submit an adviser intake with a client name + problem,
the adviser researches the client publicly (Tavily) before proposing the
team. Public research and confidential uploads stay in separate steps;
client-confidential text is never used as a search query.

## Acceptance
- Given the intake includes `client_name` + optional `website`, the adviser
  first calls Tavily with query `"{client_name} company overview {industry?}"`
  and pulls the top ~5 result snippets + URLs.
- The confidential problem statement + any uploaded notes are NOT included
  in the Tavily query — enforced by a helper `public_search_terms(intake)`.
- The Tavily response is stored in `adviser_estimate.sources` as a JSON
  array of `{url, title, snippet}` — same shape as the current stub.
- Bedrock is then called with a system prompt that includes the public
  research + the confidential intake; the LLM proposes roles as JSON.
- If Tavily is unavailable (TAVILY_API_KEY missing OR 5xx), fall back to
  the existing stub path with a note in the response `sources = []` and
  `research_status = "unavailable"`. Never invent sources.
- Test: mocked Tavily returns 5 results → sources array populated with 5
  entries; failing Tavily → empty sources + status flag.
- Test: `public_search_terms(intake_with_secret_notes)` returns terms
  containing only client_name/website — assert secret text absent.

## Config
- New env: `TAVILY_API_KEY` (Secrets Manager). Add stub in tests.
- API base: `https://api.tavily.com/search`.

## Notes
- Blueprint §5 guardrails: "Public research and confidential uploads run in
  separate steps. Client-confidential text is never put into a search
  query."
