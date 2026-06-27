# How to <do the thing this phase builds>

> One line: what this achieves and where it fits in the overall build.

**Phase:** <NN — phase name from docs/learning-spec.md>
**Concept it taught:** <the senior concept — e.g. idempotency, the N+1 problem, cache invalidation>
**Why it matters:** <1–2 sentences — the interview angle; why a senior engineer cares>

## Prerequisites

- <tools / versions needed>
- <earlier phases or files this builds on>

## Steps

### 1) <First step — short imperative title>

```bash
<commands, if any>
```

```python
<final code arrived at, if any>
```

**Why:** <the decision behind this step — not just what, but why this way. Note any
alternative considered and why it was rejected.>

### 2) <Next step>

...repeat the pattern: command/code block, then a short **Why** note...

## Run & verify

- <how to confirm it works: endpoint to hit, test to run, expected output>
- <what "success" looks like>

## Troubleshooting (real issues we hit)

- **<Symptom / error message>** → <root cause and the fix>
- <add each genuine problem encountered during this phase; future-you and others will
  hit the same ones>

## Interview talking point

<1–2 sentences you could actually say in an interview, drawn from having done this —
e.g. "I deliberately reproduced an oversell with two concurrent checkouts, then closed
the window with SELECT ... FOR UPDATE; here's the tradeoff vs an atomic update.">
