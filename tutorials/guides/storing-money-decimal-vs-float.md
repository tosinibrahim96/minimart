# Storing money: Decimal vs float (and `Numeric(10, 2)`)

> A cross-cutting how-to that surfaced building the product `price` in Phase 1. It applies
> anywhere money lives — and it comes back hard in **Phase 7** (checkout totals computed
> server-side across many line items).

## The rule

**Never store or compute money as a floating-point number. Use a fixed-precision decimal.**

- **Model (SQLAlchemy):** `price: Mapped[Decimal] = mapped_column(Numeric(10, 2))`
- **Schema (Pydantic):** `price: Decimal`
- **Imports:** `from decimal import Decimal`, `from sqlalchemy import Numeric`

## Why float is wrong for money (from the ground up)

### Start with what you already know: decimal (base 10)

When you write `0.1`, our number system is **base 10** — each place after the point is a power of
10: tenths (1/10), hundredths (1/100), thousandths… So `0.1` means "1 in the tenths place" = 1/10.
We use base 10 because we have 10 fingers — it's a human habit, nothing more.

### Computers use base 2 (binary)

A computer only has two states (on/off, 1/0), so it counts in **base 2**, where each place after
the point is a power of *2*: halves (1/2), quarters (1/4), eighths (1/8), sixteenths… To store a
number, the computer must build it out of **halves, quarters, eighths…** added together.

### The crux: which fractions "fit" depends on the base

In *any* base, some fractions write out neatly and others go on forever. You already accept this in
base 10 — what's `1/3`?

```
1/3 = 0.33333333…   ← never ends, no matter how many digits
```

Now flip it: try to build `0.1` (one tenth) out of halves, quarters, eighths… (base 2):

```
1/16 = 0.0625   → running total 0.0625  (under 0.1, keep)
+1/32 = 0.03125 → 0.09375               (still under, keep)
+1/64 → 0.109375  too big, skip
…keeps going, never lands exactly on 0.1
```

So in binary, `0.1` is an **infinite, never-ending** expansion — `0.000110011001100…` — exactly the
way `1/3` never ends for us. `0.1` is "nice" to humans but not to a computer.

> **Rule of thumb (optional):** a fraction ends cleanly only if its denominator is built from the
> base's prime factors. Base 10 = 2×5 (so 1/2, 1/5, 1/10 are clean); base 2 = only 2 (so *only*
> powers of 2 — 1/2, 1/4, 1/8 — are clean). `1/10` has a `5` in it → no clean binary form.

### The ruler analogy

- **Binary ruler:** tick marks at 1/2, 1/4, 1/8, 1/16… You can hit those exactly, but never land
  your pencil exactly on 1/10 — you stop at the nearest tick, a hair off.
- **Decimal ruler:** tick marks at tenths. You hit 0.1 dead-on, but could never mark exactly 1/3.

Neither ruler is "wrong"; the points you can hit *exactly* just depend on the tick marks (the base).
A `float` is the binary ruler; a `Decimal` is the decimal ruler.

### So a float *rounds* 0.1 — and the error compounds

Because `0.1` never ends in binary and a float has limited space, the computer chops it off and
stores the closest it can (the value stored for `0.1` is secretly `0.1000000000000000055…`). One
number, you never notice — but **sum many** and the errors add up:

```python
>>> 0.1 + 0.2
0.30000000000000004                        # float — approximate
>>> sum(0.10 for _ in range(10))           # ten dimes...
0.9999999999999999                         # ...not 1.00

>>> from decimal import Decimal
>>> Decimal("0.1") + Decimal("0.2")
Decimal('0.3')                             # exact
>>> sum(Decimal("0.10") for _ in range(10))
Decimal('1.00')                            # exact
```

Across thousands of orders, taxes, and discounts, those fractional-cent drifts mean your totals
don't reconcile. `Decimal` stores the actual base-10 digits ("a 1 in the tenths place"), so it's
**exact for the numbers humans write** — slower and bigger, but that's what money needs.

**One-liner to remember:** *float is a fast approximation on the binary ruler; Decimal is an exact
value on the decimal ruler. Money lives on the decimal ruler.* "How do you store money?" is a
near-guaranteed interview question; "floats — never; fixed-precision decimal" is the senior answer.

*(An equally valid alternative some systems use: store integer **cents** — `1999` means `$19.99` —
and do all math in integers. Both beat float. `Decimal` is more readable.)*

## float vs int vs Decimal, in one table

| Type | Stores | Exact? | Good for |
|------|--------|--------|----------|
| `int` | whole numbers | ✅ | counts, stock, IDs |
| `float` | base-2 approximation | ❌ | measurements, science |
| `Decimal` | base-10 exact | ✅ | **money** |

## What `Numeric(10, 2)` means

`Numeric(precision, scale)`:
- **precision (10)** = total number of digits (both sides of the decimal point).
- **scale (2)** = how many of those digits are after the point.

So `Numeric(10, 2)` = up to 10 total digits, exactly 2 after the point → max **8 digits before**
the point (`99,999,999.99`), always stored to the cent.

| Value | `Numeric(10,2)`? |
|-------|------------------|
| `19.99` | ✅ stored exactly |
| `12345678.99` | ✅ (10 digits) |
| `123456789.99` | ❌ 11 digits — overflow error |
| `19.999` | ⚠️ rounds to `20.00` (scale is 2) |

Versus `FLOAT`, where `19.99` might physically be `19.989999999998` and there's no fixed number
of decimal places. `Numeric` makes the database **enforce the money shape**.

## `Mapped[Decimal]` vs `mapped_column(Numeric(10, 2))` — the two halves

```python
price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
#      └── Python side ─┘             └── database side ─┘
```

- **`Mapped[Decimal]`** = the **Python type** — reading `product.price` gives you a `Decimal`.
- **`mapped_column(Numeric(10, 2))`** = the **SQL column type** — the column is `NUMERIC(10,2)`
  in Postgres.

SQLAlchemy bridges the two: reads `NUMERIC` → hands you a `Decimal`; you set a `Decimal` → it
writes `NUMERIC`. (For simple types like `int`/`str`, SQLAlchemy can *infer* the SQL type from
`Mapped[...]`, which is why `id: Mapped[int]` needs no explicit type. For `Numeric` you must be
explicit because it can't guess your precision/scale.)

## Scale rounding: the silent penny problem

`scale=2` stores **exactly 2 decimal places**. Hand the column *more* decimals and Postgres
doesn't reject them — it **silently rounds** to fit:

```
19.999  →  20.00     (third decimal rounds .99 up to 1.00)
19.994  →  19.99     (rounds down — stays)
```

Note the asymmetry between the two arguments:

| You exceed… | What happens |
|-------------|--------------|
| **scale** (too many *decimals*, e.g. `19.999`) | **silently rounds** to 2 places |
| **precision** (too *big*, e.g. `123456789.99` in `Numeric(10,2)`) | **errors** — "numeric field overflow" |

**Is this bad?** For a *price you store directly*, no — money only has two decimal places, so
you'd store `19.99`, never `19.999`, and rounding to the cent is correct. It bites only when you
**compute** money and the result has fractional cents. The classic "penny problem":

- A $10.00 item sold "3 for the price of 2" → each unit is `10.00 / 3 = 3.3333…` → stored as
  `3.33` → `3 × 3.33 = 9.99`, not `10.00`. A penny vanished.
- 10% off `19.99` → discount `1.999` → stored as `2.00`. A cent appeared.

If line items and the order total each get rounded *independently and silently*, they can disagree
by a penny — a real "the items don't add up to the total" support ticket.

**The rule:** keep `Numeric(10, 2)` for stored prices, but when you **compute** money (totals, tax,
discounts in Phase 7) do the rounding **explicitly in code**, so it's a deliberate business
decision — not an accident of the column type:

```python
from decimal import Decimal, ROUND_HALF_UP

discounted = (price * Decimal("0.9")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
```

Then *you* decide when and how to round (per line? on the final total?), and everything reconciles.

## The one surprise: Decimal serializes to a JSON *string*

Pydantic v2 serializes `Decimal` to a JSON **string** by default, to preserve exactness:

```json
{ "price": "79.99" }
```

That's not a bug — many payment APIs represent money as strings for exactly this reason. Don't
be thrown when the response shows `"79.99"` instead of a bare number.

## Interview talking point

"I use `Numeric`/`Decimal` for money because floats are base-2 approximations that can't
represent decimal values exactly, and the rounding error compounds when you sum an order
server-side. `Numeric(10, 2)` makes the database enforce two-decimal precision, and Pydantic
serializes it as a string to preserve exactness."
