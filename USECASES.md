# Use cases — type minimally, get a quick answer

The bot remembers the current chat. **Say it once, then type only what changes.** You don't have to
repeat the city or the activity on every message; the graph carries them forward and you change just
the one thing you care about next.

> Everything below is real behaviour captured from the running graph. The weather numbers in the
> worked example come from a fixed test snapshot; against the live app the numbers and which SOP fires
> depend on the actual Open-Meteo data for your city at that moment. The *interaction pattern* is the point.

## The one rule

- **First message:** name an **activity** and a **place** (a question word is optional). Terse is fine —
  `drive in bhopal?` is enough.
- **After that:** type only the **delta** — a new time, a new place, or a new activity. The rest is inherited.
- **Ask `why?`** any time to get the SOP citation and the exact numbers behind the last answer.
- **"New chat"** (sidebar button) wipes the memory and starts fresh.

## Minimal first messages that work

| You type | The bot understands |
|---|---|
| `drive in bhopal?` | driving + Bhopal + "is it safe?" |
| `walk the dog in delhi?` | pet walk (with a pet) + Delhi |
| `photos in bhopal tonight?` | outdoor photography + Bhopal + tonight |
| `camping in manali this weekend` | camping + Manali + overnight window |
| `electrical work outside in pune?` | outdoor electrical work + Pune |

You write intent in plain words; you never have to learn policy names or field names. Paraphrases work —
`I ride a scooter to work, gusty today?` reaches the same wind policy as formal wording.

## A real session (each follow-up is tiny)

```
YOU: drive in bhopal?
BOT: Bhopal, Madhya Pradesh, India – 2026-09-04 13:30 local. Today: visibility is 400 m in
     fog, so driving conditions are poor; slow down, use low-beam headlights, increase
     following distance and delay non-essential travel. [WA-01]

YOU: tonight?                      ← kept: place + activity. changed: time
BOT: Bhopal … [WA-01] Visibility is 400 m in fog … (re-checked for tonight)

YOU: what about Delhi?             ← kept: activity + time. changed: place
BOT: Delhi, Delhi, India … [WA-01] Visibility is 400 m in fog …

YOU: why?                          ← no weather question, just explain the last answer
BOT: I said that because of WA-01 (Dense-fog road visibility; severity warning; primary):
     the hazard is impaired visibility … Evidence from the weather data for Delhi: visibility = 400.
```

What was inherited at each step (from the actual trace): `tonight?` reused **location + activity +
question type**; `what about Delhi?` reused **activity + question type + time**; `why?` reused everything
and routed to the explanation path.

## Follow-up cheat-sheet

| Goal | Minimal thing to type | What's reused |
|---|---|---|
| Same question, different time | `tonight?` / `tomorrow?` / `this morning?` | place, activity |
| Same question, different place | `what about Delhi?` / `in Pune?` | activity, time |
| Same place/time, different activity | `and a run?` / `cycling instead?` | place, time |
| Explain the last answer | `why?` / `what's that based on?` | everything (citation only) |
| Start over | click **New chat** | nothing (memory reset) |

## What's required vs optional

- **Required on the first message:** an activity and a place. If the place is missing the bot asks for
  it (`Please provide the city …`) rather than guessing; if no activity/situation is given it asks what
  you're asking about.
- **Optional anywhere:** the time (defaults to *today*), the question phrasing, punctuation, capitalisation.

## Honest edges (the bot won't bluff)

- **No policy covers it** → it says so plainly (`I do not have a policy that applies …`), it does **not**
  invent advice.
- **Off-topic** (`capital of France?`) → it declines: `I can only advise on outdoor activities and
  weather-related safety.`
- **Can't resolve the city / weather API down** → it says it can't check, rather than giving a made-up
  forecast.
- **Required data missing** → it says a policy couldn't be fully evaluated (and `why?` names which one).
- **Every number it reports is from the live API for that request**, and every answer is traceable to a
  specific SOP — that's why `why?` always has a real citation to hand.

## Tips for the fastest turnaround

- Lead with the activity and city; add a time only if it isn't "today".
- For follow-ups, a single word or short phrase is enough — don't re-type the whole question.
- Replies are kept short (under ~100 words); open **"Why this answer"** in the UI for the full trace
  (matched SOPs, evidence, the exact weather request).
