# Filtering vs Search: How Stripe, GitHub & Google Design List APIs

> Cross-cutting design guide. Born during Phase 2 when researching how top APIs do
> filtering — the research found "the best APIs use strings," which turned out to be
> half-right in an instructive way. Phase 2 builds one half of this; Phase 16 builds the other.

## The claim, and what the evidence actually says

Researching Stripe, Google, and GitHub suggests "the best APIs filter with query *strings*,
not structured params." Look closer and all three run **both** patterns side by side, split
by job:

**Stripe.** Everyday **list** endpoints use structured parameters:

```
GET /v1/charges?customer=cus_123&created[gte]=1656000000&limit=10
```

The string query language lives on separate, dedicated **Search** endpoints:

```
GET /v1/charges/search?query=amount>999 AND metadata['order_id']:'6735'
```

— and Stripe documents search as a different beast: backed by a search index, *eventually
consistent* (a just-created charge may not appear for a minute), available only on some
resources.

**GitHub.** Listing issues on a repo is structured params
(`GET /repos/{o}/{r}/issues?state=open&labels=bug`). The qualifier string
(`q=repo:foo state:open label:bug`) lives on `/search/*` — the search endpoints, backed by
their Elasticsearch cluster, with separate rate limits.

**Google.** The one true exception: [AIP-160](https://google.aip.dev/160) puts a filter
*string* (`?filter=price < 100 AND category = "electronics"`) on ordinary list endpoints.
But Google amortizes a formal grammar, a shared parser library, and a spec document across
hundreds of resource types and generated clients in ten languages. AIP-160 solves "we have
400 list endpoints and can't hand-design filters for each."

**The accurate rule:** structured parameters for *filtering* (bounded, known fields);
a string query language for *search* (open-ended, index-backed). Google's exception is paid
for with Google-scale infrastructure.

## Why the split exists (from first principles)

With structured params in FastAPI, the framework does parsing, type coercion, validation,
and error messages — `?min_price=abc` earns a field-level `422` you wrote zero lines for,
and every param lands in the OpenAPI docs automatically. A filter is just an input schema
for a read.

With a filter string, everything Pydantic gave you, you now owe by hand:

1. **A grammar and a parser** — you're maintaining a small language.
2. **Validation with good errors** — "syntax error near position 23" replaces field-level detail.
3. **A field whitelist and safe SQL translation** — map `price >= 50` to a column from an
   allowlist, never by string-building SQL, or you've invented a SQL-injection front door.
4. **Documentation** — OpenAPI can describe "a string," not your grammar. You write prose.

**Analogy:** structured params are a paper form with labelled boxes — the clerk (FastAPI)
rejects a bad form instantly, box by box. A filter string is a blank line saying "describe
what you want" — infinitely flexible, but now you need a trained clerk (your parser) with a
procedure for every way it can be misread or abused. Hire that clerk only when the labelled
boxes truly can't express what customers ask.

## Pros and cons, honestly

| | Structured params | Filter string / query language |
|---|---|---|
| Validation & 422s | free (framework) | hand-built |
| OpenAPI docs | automatic | prose only |
| Parsing / security | none needed / no parser surface | grammar + whitelist + injection care |
| Expressiveness | implicit AND, operators baked into names (`min_price`, Stripe's `created[gte]`) | OR/NOT/nesting/ranges in one param |
| Scales across huge API surface | each endpoint hand-designed | one grammar amortized (Google's reason) |
| Client experience | curl-able, browser-testable | power-user affordance (GitHub's search box *is* the syntax) |

## The decision rule (the interview answer)

> Bounded filtering over a handful of known fields → structured parameters. Open-ended
> querying, a huge uniform API surface, or genuine text search → a query language, almost
> always backed by a search index rather than your OLTP database. Expressiveness is bought
> with parsing, security, and documentation burden — pay only when filtering's ceiling
> actually constrains users.

Related boundary, same judgement: `ILIKE '%term%'` on a dozen-row lookup table's `name` is
*filtering* — cheap, fine forever. `ILIKE` across 100k products' names and descriptions
pretending to be search is the anti-pattern Phase 16 replaces with Postgres FTS
(`tsvector` + GIN). Same operator, different job.

## How MiniMart maps onto this

- **Phase 2 (built):** structured filters on `GET /products` and `GET /categories` —
  `category_id`, `min_price`/`max_price`, `in_stock`, `name` contains. This *is* what Stripe
  and GitHub do on list endpoints; a filter DSL here would import Google's solution without
  Google's problem. See `tutorials/phases/product-catalog-write.md` steps 9–10 for the
  implementation pattern (conditions list, drift-proof count, wildcard escaping).
- **Phase 16 (later):** the string flavor — `GET /products/search?q=` through a real text
  pipeline (parsing, stemming, ranking). The `q=` is a string because the input *is*
  language, not a field comparison.
- Naming middle-ground worth knowing: Stripe's `created[gte]` bracket style is structured
  params with operator suffixes. FastAPI doesn't parse bracket syntax; the Pythonic spelling
  is `min_price`/`max_price` (or `price_gte`). Pick one convention and keep it.

## Reference

The pinned community-standard repo (zhanymkanov/fastapi-best-practices) backs the adjacent
principle used in Phase 2's implementation: **"SQL-first, Pydantic-second"** — filtering,
counting, and aggregation happen in SQL, not by fetching rows and processing in Python; its
example even builds nested JSON responses inside Postgres (`json_build_object`), a technique
to weigh against ORM composability when Phase 10 profiles the read path.
