# The Session Record — Conversation Intake & Analytics

**Addition to** [`SPEC.md`](./SPEC.md). Everything there still holds; this adds one table pair, one extraction call, and one rule about when identity is allowed to be written.

---

## 1. Why this exists

The concierge conversation is a far richer signal than a web session. To sell someone a kit the agent must find out what they are actually doing: the sport, where, when, with how many people, what they already own, what they refused and why, and what we could not sell them at all.

That is the second product. The cart is what Decathlon buys first; **the intake is what makes it worth renewing.**

Two audiences, two different retention needs:

| | Question it answers | Needs identity? |
|---|---|---|
| **Merchandising / marketing** | What are people trying to do, and what can't we sell them? | **No** — aggregate only |
| **Returning-customer experience** | What does *this* person already own and wear? | **Yes** — but only if they bought |

The whole design follows from that split.

---

## 2. The rule: never-write, not delete-later

> **A session record is written from the first turn and never contains identity.
> Identity is written only if the conversation converts.**

The naive version of this is "store everything, delete the identity if they don't buy." That needs a deletion job, a retention clock, and a race between the job and anything already reading the row. It also means the sensitive write happened — you are trusting a cleanup process.

We invert it. Identity lives **only in volatile session state** for the duration of the conversation. The `session_record` row is written without it. On conversion — and only then — a `customer_profile` row is created and the foreign key is set.

**If the conversation does not convert, there is nothing to delete, because the link was never written.** No cron, no retention clock, no race. The privacy property is structural rather than procedural, which is also why it is easy to demo: point at the schema and show that the write path simply does not exist on the non-converting branch.

```
conversation starts
   │
   ├─ session_record INSERT ............ always. no identity. ever.
   │
   ├─ identity (sizes, customer ref) ... held in Reflex State only. never persisted.
   │
   └─ conversion?
         ├─ no  → session state discarded. record stays, anonymous. done.
         └─ yes → customer_profile INSERT + session_record.customer_profile_id = id
```

---

## 3. What counts as a conversion

Be honest about this, because it is a real limitation of the integration rather than a design choice.

We **cannot observe payment.** `complete_checkout` and `get_order` are JWT-gated (`SPEC.md` §3.1), and the flow deliberately ends by handing over a cart link. So the furthest thing we directly observe is that we created a cart.

Three outcomes, only the first two of which we can see by ourselves:

| `outcome` | Meaning | Observed how |
|---|---|---|
| `abandoned` | No cart was built | Session ended, no `create_cart` |
| `cart_created` | We built a real cart and handed over the link | Our own `create_cart` call succeeded |
| `converted` | The buyer actually purchased | **External signal — see below** |

`converted` is set by one function, so the signal source can be swapped without touching anything else:

```python
# analytics/conversion.py
def conversion_signal(cart_id: str) -> bool:
    """Demo: the buyer tells us. Production: Shopify order webhook keyed on cart_id."""
    return _confirmed_in_ui.get(cart_id, False)
```

For the demo, the honest and demonstrable version is an explicit **"I completed my purchase"** confirmation in the UI after the cart hand-off. In production this is a Shopify order webhook. Say this out loud rather than implying we can see orders — a judge who has read `agents.md` will know we cannot.

**Identity is gated on `converted`, not on `cart_created`.** A cart that was never paid for is not a customer relationship.

---

## 4. Schema

Two tables, plain SQLModel, SQLite. Verified working.

```python
# analytics/models.py
import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, Session, create_engine

class CustomerProfile(SQLModel, table=True):
    """Written ONLY on conversion. This table is the identity boundary."""
    id: Optional[int] = Field(default=None, primary_key=True)
    customer_ref: str = Field(index=True)      # opaque ref, not an email
    sizes_json: str = "{}"                     # {"footwear": "9.5", "top": "M"}
    disciplines_json: str = "[]"               # accumulated across purchases
    owned_gear_json: str = "[]"                # what they told us they already have
    home_region: str = ""
    typical_budget_minor: Optional[int] = None
    first_seen: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    last_seen: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)


class SessionRecord(SQLModel, table=True):
    """Written for EVERY conversation, from the first turn. Never identifiable."""
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)        # random per conversation
    started_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    turn_count: int = 0

    # ─ intent
    discipline: str = ""                       # "mountain hiking", "trail running"
    environment: str = ""                      # alpine, open_water, road...
    location_text: str = ""                    # free text, only if volunteered
    trip_month: str = ""                       # seasonality
    party_size: int = 1
    solo: bool = True
    overnight: bool = False

    # ─ what they brought and wanted
    already_owned_json: str = "[]"             # gear slots they said were covered
    slots_requested_json: str = "[]"
    budget_minor: Optional[int] = None

    # ─ what happened
    products_shown_json: str = "[]"            # variant GIDs
    products_accepted_json: str = "[]"
    unservable_slots_json: str = "[]"          # ← the sellable signal, see §6
    friction_json: str = "[]"                  # size substitutions, budget gaps, rejections
    sentiment: str = "neutral"                 # positive | neutral | frustrated
    sentiment_note: str = ""

    # ─ outcome
    outcome: str = "abandoned"                 # abandoned | cart_created | converted
    cart_id: str = ""
    cart_total_minor: Optional[int] = None

    # ─ the identity boundary. NULL unless outcome == "converted".
    customer_profile_id: Optional[int] = Field(default=None,
                                               foreign_key="customerprofile.id")

engine = create_engine("sqlite:///analytics.db")
SQLModel.metadata.create_all(engine)           # one line, no migrations, no alembic
```

JSON-in-TEXT columns are deliberate. At this scale it keeps the schema to two tables with no joins, and SQLite reads them fine with `json_extract` when you want to aggregate.

---

## 5. Extraction — one call at session end

One structured-output call, the same verified pattern as the `ActivityProfile` extraction in `SPEC.md` §4.4: `response_schema` with a Pydantic model, **no tools**, returns a typed instance on `.parsed`.

```python
# analytics/extract.py
class SessionInsight(BaseModel):
    discipline: str = ""
    environment: str = ""
    location_text: str = ""          # "" if never volunteered — do NOT infer
    trip_month: str = ""
    party_size: int = 1
    overnight: bool = False
    already_owned: list[str] = []
    slots_requested: list[str] = []
    unservable_slots: list[str] = []
    friction: list[str] = []
    sentiment: Literal["positive", "neutral", "frustrated"] = "neutral"
    sentiment_note: str = ""

def extract(transcript: str) -> SessionInsight:
    return client.models.generate_content(
        model=MODEL, contents=EXTRACT_PROMPT + transcript,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SessionInsight)).parsed
```

Two prompt rules that matter more than the schema:

- **Never infer.** If the user did not say where they are going, `location_text` is `""`. An inferred location silently poisons the geographic analytics, and it is the field most tempting to guess from context.
- **Sentiment is about the shopping experience**, not the trip. "The páramo is brutal" is enthusiasm about the hike; "none of this fits my budget" is frustration with us. Only the second is a signal we can act on.

`unservable_slots` and `friction` come from the guardrails, not the model — `guardrails.py` already computes them (`SPEC.md` §6.1). Pass them in rather than asking the model to re-derive what we already know deterministically.

---

## 6. What this opens — the analytics door

The pitch is not "we log conversations." It is that a concierge conversation captures **demand for things you do not stock**, which no clickstream can, because a shopper who cannot find goggles simply leaves and is never counted.

Our own catalog survey found the gaps: swimming is four microfiber towels, climbing is absent, and there are no bike helmets in stock (`SPEC.md` §1.2). Every conversation that asks for them becomes a row.

```sql
-- Unmet demand, ranked. The single most sellable query in this schema.
SELECT json_each.value AS missing_item, COUNT(*) AS asked_for
FROM sessionrecord, json_each(sessionrecord.unservable_slots_json)
GROUP BY missing_item ORDER BY asked_for DESC;

-- Where abandonment happens
SELECT outcome, sentiment, COUNT(*) FROM sessionrecord GROUP BY 1, 2;

-- Price sensitivity: stated budget vs what they actually accepted
SELECT discipline, AVG(budget_minor), AVG(cart_total_minor)
FROM sessionrecord WHERE outcome != 'abandoned' GROUP BY discipline;

-- Seasonality and geography of intent
SELECT trip_month, discipline, COUNT(*) FROM sessionrecord
WHERE location_text != '' GROUP BY 1, 2;
```

The returning-customer side is narrower and only exists for converted buyers: pre-fill sizes, skip the questions they already answered, and know what they own so the agent stops recommending a second rain shell. That is the friction the profile removes — and the reason it is worth asking permission for, because they bought.

---

## 7. Where it plugs in

Four small additions to the layout in `SPEC.md` §8. Budget **~30 minutes**, in the 02:20–02:50 hardening block — after the cart works, never before.

```
concierge/
  analytics/
    models.py        # the two tables above
    extract.py       # SessionInsight + the one extraction call
    conversion.py    # conversion_signal() — the swappable gate
    record.py        # open_session / update / close_session
```

```python
# analytics/record.py — the entire identity rule, in one function
def close_session(sid: str, insight: SessionInsight, outcome: str,
                  identity: dict | None) -> None:
    with Session(engine) as s:
        rec = s.exec(select(SessionRecord)
                     .where(SessionRecord.session_id == sid)).one()
        rec.discipline = insight.discipline
        rec.sentiment  = insight.sentiment
        rec.outcome    = outcome
        # ... remaining insight fields

        if outcome == "converted" and identity:      # the ONLY write path
            prof = CustomerProfile(
                customer_ref=identity["ref"],
                sizes_json=json.dumps(identity["sizes"]))
            s.add(prof); s.commit(); s.refresh(prof)
            rec.customer_profile_id = prof.id

        s.add(rec); s.commit()
```

Add `sqlmodel` to `requirements.txt`. Note that Reflex ships `rx.Model`, but it is **deprecated — "will be completely removed in 1.0.0"** — and expects `reflex db init` with alembic. Plain SQLModel is fewer moving parts and no migration step.

---

## 8. Guardrails

Same principle as `SPEC.md` §6 — enforced in code, not in the prompt.

| Guardrail | Enforced in | Behaviour |
|---|---|---|
| **Identity write gate** | `record.py` | `customer_profile_id` is set on exactly one branch: `outcome == "converted"`. Nothing else in the codebase writes it |
| **No identity in the transcript** | `record.py` | Scrub email/phone patterns before persisting. The agent never asks for them (`SPEC.md` §6.2), so anything present was volunteered by accident |
| **No inferred location** | `extract.py` prompt | `location_text` stays `""` unless stated. Inferred geography is worse than missing geography |
| **Analytics never blocks the sale** | `record.py` | Every call wrapped; a failed extraction or DB write logs and returns. The concierge must never break because the logger did |
| **Deterministic fields are not model-derived** | `record.py` | `unservable_slots`, `friction`, totals and outcome come from the guardrails and the cart, never from the extraction call |

The last two are the ones that bite. An analytics layer that can take down the product it measures is worse than no analytics layer, and a model asked to re-derive a number the code already knows will eventually disagree with it.

---

## 9. Demonstrating it

Worth ninety seconds at the end of the demo, because it is the part that sounds like a business rather than a hackathon project.

1. Run a conversation that **does not convert**. Show the row: full intent, sentiment, unmet demand — and `customer_profile_id = NULL`.
2. Run one that **does**. Show the profile row appear and the FK populate.
3. Run the unmet-demand query. *"Four people asked us for swimming goggles this morning. Decathlon US doesn't stock them. No analytics product you currently own can tell you that, because those shoppers never searched — they asked a person."*
4. Point at `close_session`: the identity write exists on exactly one branch. **The privacy guarantee is a property of the code, not a policy in a document.**

---

## Provenance

The schema and both persistence paths were executed locally on 25 July 2026: `SQLModel.metadata.create_all` against SQLite, inserts on both branches, and confirmation that a non-converting session yields `customer_profile_id = NULL` while a converting one populates the foreign key. `rx.Model` was tested and works but emits a removal-in-1.0.0 deprecation warning and requires `reflex db init`. The conversion signal is **not** verified end-to-end — Decathlon exposes no order read to us (`get_order` is JWT-gated), which is precisely why §3 makes it a single swappable function.
