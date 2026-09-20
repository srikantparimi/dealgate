# Golden GM fixtures

One directory per scenario: `input.json` describes the engagement, and
`expected.json` records what the gross margin must come to.

**The expected values are computed by hand, never by the engine.** A golden
generated from the code under test only proves the code agrees with itself;
it cannot catch a wrong rule. Every number in every `expected.json` was
worked out independently and is reproducible with a calculator from the
`workings` string carried alongside it.

Money is a decimal string everywhere, never a float (CLAUDE.md rule 2).
Percentages are stored as ratios (`"0.1040"` = 10.40%) so no rounding happens
before the floor test — `35.000%` passes and `34.9999%` fails, and a value
rounded to two places on the way in would erase that distinction.

`status` is one of:

- `ok`         — every input present, the margin is a number.
- `incomplete` — a required input is absent. `missing` names the field and
                 the line it belongs to. No margin is presented as final.
- `exception`  — revenue is zero, negative or absent. Not a percentage:
                 dividing by it would be meaningless, and showing `0.0%`
                 reads as a real and very bad margin rather than as "there is
                 nothing to divide by".

Source: `docs/gm-rules.md`, generated from the same rule table the engine
reads.
