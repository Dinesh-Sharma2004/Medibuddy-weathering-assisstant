# Use cases — type minimally, get a quick answer

The bot remembers the current chat. **Say it once, then type only what changes.** You don't have to
repeat the city or the activity on every message; the graph carries them forward and you change just
the one thing you care about next.

> Everything below is real behaviour captured from the running graph. The weather numbers in the
> worked example come from a fixed test snapshot; against the live app the numbers and which SOP fires
> depend on the actual Open-Meteo data for your city at that moment. The *interaction pattern* is the point.

## Important: when you get advice vs "no guidance"

Each policy fires only when its **weather condition is actually met** — fog with low visibility, wind at
or above the cycling threshold, a thunderstorm, a sub-zero morning, and so on. So on a calm, ordinary day
the honest answer to most questions is **"I do not have a policy that applies to those conditions and
activity."** That is the bot working correctly, not a failure: it never invents advice just to have
something to say. To see advice, ask about an activity whose hazard is live right now (e.g. cycling when
it's genuinely windy, driving when there's fog, any outdoor plan during a storm). The examples below show
the *shape* of the conversation; whether a given one returns advice depends on today's weather.

## The one rule

- **First message:** name an **activity** and a **place** (a question word is optional). Terse is fine —
  `drive in bhopal?` is enough.
- **After that:** type only the **delta** — a new time, a new place, or a new activity. The rest is inherited.
- **Ask `why?`** any time to get the SOP citation and the exact numbers behind the last answer.
- **"New chat"** (sidebar button) wipes the memory and starts fresh.

## Minimal first messages that work

| You type | The bot understands | Advice appears when… |
|---|---|---|
| `cycle in bhopal?` | cycling/two-wheeler + Bhopal | it's windy (≥ the policy threshold) |
| `drive in bhopal?` | driving + Bhopal | there's fog / snow / ice |
| `walk the dog in delhi?` | pet walk (with a pet) + Delhi | hot pavement or snow underfoot |
| `photos in bhopal tonight?` | outdoor photography + Bhopal + tonight | conditions score as favourable |
| `camping in manali this weekend` | camping + Manali + overnight window | the overnight low is cold |
| `electrical work outside in pune?` | outdoor electrical work + Pune | it's raining |

Even a bare statement with no question works — `driving a car`, `thinking of cycling`, `travelling to
Bhopal` are all understood; if you leave out the city the bot asks for it rather than guessing. You write
intent in plain words and never learn policy names. Paraphrases work too — `I ride a scooter to work, gusty
today?` reaches the cycling wind policy (WA-21).

## Quickest way to see it answer right now

The surest demo is the **fuzzy photography policy (WA-19)** — its score turns favourable on most fair-weather
days, so it returns advice in almost any city:

```
is today a good day for photography in Bhopal?
→ outdoor photography conditions are excellent [WA-19]   (works in Delhi, Mumbai, London, … too)
```

Other reliable ones, if the matching weather is live: **dog walk in a hot city** (`is it okay to walk my
dog in Singapore?` → WA-11, hot pavement) and **any outdoor plan during a storm** (→ WA-20 override).

## Example query for every policy (what each SOP needs)

The bot answers only when the policy's weather condition is actually live. Pick the row that matches today's
weather where you are (or try a city that has it):

| Ask something like… | Fires | Needs this weather |
|---|---|---|
| `is today good for outdoor photography in <city>?` | WA-19 | fair conditions (fires most days) |
| `is tonight good for stargazing in <city>?` | WA-18 | clear night, low cloud, good visibility |
| `is it safe to cycle / ride my scooter in <city>?` | WA-21 | wind ≥ 35 km/h (windy/coastal) |
| `is it safe to drive in <city>?` | WA-01 | fog with low visibility |
| `should I drive to <city> in this snow?` | WA-02 | snow squall (snow + low vis + gusts) |
| `is the road safe, it's freezing and sleeting?` | WA-03 | freezing precipitation, temp ≤ 0 |
| `is it safe to play cricket in <city>?` | WA-04 | hail / thunderstorm code |
| `is it okay to trek <mountain> today?` | WA-05 | fresh snowfall over the window |
| `can I hike the snow trail at <place>?` | WA-06 | snow already on the ground |
| `is it okay to camp overnight in <cold place>?` | WA-07 | cold overnight (apparent ≤ 5 °C) |
| `should I cover my garden plants in <city> tonight?` | WA-08 | frost (daily min ≤ 2 °C) |
| `is it safe to do heavy outdoor work in <hot city>?` | WA-09 | high wet-bulb (≥ 28 °C) |
| `I'm a new outdoor worker in <hot city>, safe today?` | WA-10 | apparent ≥ 30 °C + "new/returning worker" |
| `is it okay to walk my dog in <hot city>?` | WA-11 | hot pavement (surface ≥ 45 °C) |
| `walk the dog, there's snow on the ground?` | WA-12 | snow depth + snowing |
| `my kids are waiting outside in <cold city>, okay?` | WA-13 | cold (apparent ≤ 8 °C) + children |
| `can my elderly parent go out in <cold city>?` | WA-14 | cold (apparent ≤ 5 °C) + elderly |
| `is it safe to do outdoor electrical work, it's raining?` | WA-15 | any current precipitation |
| `setting up a canopy/tent in <windy city>, safe?` | WA-16 | gusts ≥ 45 km/h |
| `can I cross the stream on my trail after this rain?` | WA-17 | ≥ 10 mm rain over the window |
| `is it safe to go out in <city> during this storm?` | WA-20 | thunderstorm + gust/precip (leads over all) |

When the weather isn't there, you'll get an honest *"I do not have a policy that applies"* — that's correct,
not a bug. Driving, for instance, only has advice in fog/snow/ice; on a clear day it returns no guidance.

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
