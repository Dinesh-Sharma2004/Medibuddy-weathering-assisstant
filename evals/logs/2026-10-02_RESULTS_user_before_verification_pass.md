# Eval results (user suite)

- Date: 2026-10-02T03:02:46
- Model: n/a (no LLM configured for this run)
- Git SHA: no commits yet
- Mode: all; LLM runs per case: 3 (a case passes only if all runs pass)
- Summary: 1 PASS, 0 FAIL, 3 NOT RUN, 0 SKIPPED

| Case | Mode | Result |
|---|---|---|
| L3 | custom | PASS |
| L4 | custom | NOT RUN |
| L1 | custom | NOT RUN |
| S2 | live | NOT RUN |

## L3 [custom] - PASS

- **What it checks:** No SOP ID or advice string from either SOP file is hardcoded under src/.
- **Pass looks like:** Zero occurrences.
- **Details:**
  - scanned 9 files against 30 ids/advice fragments

## L4 [custom] - NOT RUN

- **What it checks:** Coverage report - which of your SOPs no case references.
- **Pass looks like:** Every SOP is named by at least one case.
- **Details:**
  - SOP file invalid, fix it first: Invalid SOP file:
  - meta.disclose_unknown_from must be one of severities ['TODO_lowest', 'TODO_middle', 'TODO_highest']
  - vocabulary.time_words.TODO_time_tag.window.start must be a whole hour 'HH:00' (end may be '24:00')
  - vocabulary.time_words.TODO_time_tag.window.end must be a whole hour 'HH:00' (end may be '24:00')
  - sop 'TODO_ID_01': id does not match meta.id_pattern 'TODO regex every SOP id must fully match, e.g. a fixed prefix; the verifier treats any text matching it as an SOP id'
  - sop 'TODO_ID_01': severity 'TODO' not in meta.severities
  - sop 'TODO_ID_01': applies_to.activities has unknown tag 'TODO_tag'
  - sop 'TODO_ID_01': applies_to.groups has unknown tag 'TODO_tag'
  - sop 'TODO_ID_01': applies_to.question_types has unknown tag 'TODO_tag'
  - sop 'TODO_ID_01': bad requires entry {'field': 'TODO', 'source': 'TODO'} (need field + source in ['current', 'daily', 'hourly'])
  - sop 'TODO_ID_01'.condition: a condition node must have exactly one key (compare, window_agg, score, all, any, not)
  - sop 'TODO_ID_01': advice placeholder {placeholders} is not produced by the condition (available: [])
  - sop 'TODO_ID_02': id does not match meta.id_pattern 'TODO regex every SOP id must fully match, e.g. a fixed prefix; the verifier treats any text matching it as an SOP id'
  - sop 'TODO_ID_02': severity 'TODO' not in meta.severities
  - sop 'TODO_ID_02': applies_to.activities has unknown tag 'TODO_tag'
  - sop 'TODO_ID_02': applies_to.groups has unknown tag 'TODO_tag'
  - sop 'TODO_ID_02': applies_to.question_types has unknown tag 'TODO_tag'
  - sop 'TODO_ID_02': bad requires entry {'field': 'TODO', 'source': 'TODO'} (need field + source in ['current', 'daily', 'hourly'])
  - sop 'TODO_ID_02'.condition: a condition node must have exactly one key (compare, window_agg, score, all, any, not)
  - sop 'TODO_ID_02': advice placeholder {placeholders} is not produced by the condition (available: [])
  - sop 'TODO_ID_03': id does not match meta.id_pattern 'TODO regex every SOP id must fully match, e.g. a fixed prefix; the verifier treats any text matching it as an SOP id'
  - sop 'TODO_ID_03': severity 'TODO' not in meta.severities
  - sop 'TODO_ID_03': applies_to.activities has unknown tag 'TODO_tag'
  - sop 'TODO_ID_03': applies_to.groups has unknown tag 'TODO_tag'
  - sop 'TODO_ID_03': applies_to.question_types has unknown tag 'TODO_tag'
  - sop 'TODO_ID_03': bad requires entry {'field': 'TODO', 'source': 'TODO'} (need field + source in ['current', 'daily', 'hourly'])
  - sop 'TODO_ID_03'.condition: a condition node must have exactly one key (compare, window_agg, score, all, any, not)
  - sop 'TODO_ID_03': advice placeholder {placeholders} is not produced by the condition (available: [])
  - sop 'TODO_ID_04': id does not match meta.id_pattern 'TODO regex every SOP id must fully match, e.g. a fixed prefix; the verifier treats any text matching it as an SOP id'
  - sop 'TODO_ID_04': severity 'TODO' not in meta.severities
  - sop 'TODO_ID_04': applies_to.activities has unknown tag 'TODO_tag'
  - sop 'TODO_ID_04': applies_to.groups has unknown tag 'TODO_tag'
  - sop 'TODO_ID_04': applies_to.question_types has unknown tag 'TODO_tag'
  - sop 'TODO_ID_04': bad requires entry {'field': 'TODO', 'source': 'TODO'} (need field + source in ['current', 'daily', 'hourly'])
  - sop 'TODO_ID_04'.condition: a condition node must have exactly one key (compare, window_agg, score, all, any, not)
  - sop 'TODO_ID_04': advice placeholder {placeholders} is not produced by the condition (available: [])
  - sop 'TODO_ID_05': id does not match meta.id_pattern 'TODO regex every SOP id must fully match, e.g. a fixed prefix; the verifier treats any text matching it as an SOP id'
  - sop 'TODO_ID_05': severity 'TODO' not in meta.severities
  - sop 'TODO_ID_05': applies_to.activities has unknown tag 'TODO_tag'
  - sop 'TODO_ID_05': applies_to.groups has unknown tag 'TODO_tag'
  - sop 'TODO_ID_05': applies_to.question_types has unknown tag 'TODO_tag'
  - sop 'TODO_ID_05': bad requires entry {'field': 'TODO', 'source': 'TODO'} (need field + source in ['current', 'daily', 'hourly'])
  - sop 'TODO_ID_05'.condition: a condition node must have exactly one key (compare, window_agg, score, all, any, not)
  - sop 'TODO_ID_05': advice placeholder {placeholders} is not produced by the condition (available: [])
  - sop 'TODO_ID_06': id does not match meta.id_pattern 'TODO regex every SOP id must fully match, e.g. a fixed prefix; the verifier treats any text matching it as an SOP id'
  - sop 'TODO_ID_06': severity 'TODO' not in meta.severities
  - sop 'TODO_ID_06': applies_to.activities has unknown tag 'TODO_tag'
  - sop 'TODO_ID_06': applies_to.groups has unknown tag 'TODO_tag'
  - sop 'TODO_ID_06': applies_to.question_types has unknown tag 'TODO_tag'
  - sop 'TODO_ID_06': bad requires entry {'field': 'TODO', 'source': 'TODO'} (need field + source in ['current', 'daily', 'hourly'])
  - sop 'TODO_ID_06'.condition: a condition node must have exactly one key (compare, window_agg, score, all, any, not)
  - sop 'TODO_ID_06': advice placeholder {placeholders} is not produced by the condition (available: [])
  - sop 'TODO_ID_07': id does not match meta.id_pattern 'TODO regex every SOP id must fully match, e.g. a fixed prefix; the verifier treats any text matching it as an SOP id'
  - sop 'TODO_ID_07': severity 'TODO' not in meta.severities
  - sop 'TODO_ID_07': applies_to.activities has unknown tag 'TODO_tag'
  - sop 'TODO_ID_07': applies_to.groups has unknown tag 'TODO_tag'
  - sop 'TODO_ID_07': applies_to.question_types has unknown tag 'TODO_tag'
  - sop 'TODO_ID_07': bad requires entry {'field': 'TODO', 'source': 'TODO'} (need field + source in ['current', 'daily', 'hourly'])
  - sop 'TODO_ID_07'.condition: a condition node must have exactly one key (compare, window_agg, score, all, any, not)
  - sop 'TODO_ID_07': advice placeholder {placeholders} is not produced by the condition (available: [])
  - sop 'TODO_ID_08': id does not match meta.id_pattern 'TODO regex every SOP id must fully match, e.g. a fixed prefix; the verifier treats any text matching it as an SOP id'
  - sop 'TODO_ID_08': severity 'TODO' not in meta.severities
  - sop 'TODO_ID_08': applies_to.activities has unknown tag 'TODO_tag'
  - sop 'TODO_ID_08': applies_to.groups has unknown tag 'TODO_tag'
  - sop 'TODO_ID_08': applies_to.question_types has unknown tag 'TODO_tag'
  - sop 'TODO_ID_08': bad requires entry {'field': 'TODO', 'source': 'TODO'} (need field + source in ['current', 'daily', 'hourly'])
  - sop 'TODO_ID_08'.condition: a condition node must have exactly one key (compare, window_agg, score, all, any, not)
  - sop 'TODO_ID_08': advice placeholder {placeholders} is not produced by the condition (available: [])
  - sop 'TODO_ID_09': id does not match meta.id_pattern 'TODO regex every SOP id must fully match, e.g. a fixed prefix; the verifier treats any text matching it as an SOP id'
  - sop 'TODO_ID_09': severity 'TODO' not in meta.severities
  - sop 'TODO_ID_09': applies_to.activities has unknown tag 'TODO_tag'
  - sop 'TODO_ID_09': applies_to.groups has unknown tag 'TODO_tag'
  - sop 'TODO_ID_09': applies_to.question_types has unknown tag 'TODO_tag'
  - sop 'TODO_ID_09': bad requires entry {'field': 'TODO', 'source': 'TODO'} (need field + source in ['current', 'daily', 'hourly'])
  - sop 'TODO_ID_09'.condition: a condition node must have exactly one key (compare, window_agg, score, all, any, not)
  - sop 'TODO_ID_09': advice placeholder {placeholders} is not produced by the condition (available: [])
  - sop 'TODO_ID_10': id does not match meta.id_pattern 'TODO regex every SOP id must fully match, e.g. a fixed prefix; the verifier treats any text matching it as an SOP id'
  - sop 'TODO_ID_10': severity 'TODO' not in meta.severities
  - sop 'TODO_ID_10': applies_to.activities has unknown tag 'TODO_tag'
  - sop 'TODO_ID_10': applies_to.groups has unknown tag 'TODO_tag'
  - sop 'TODO_ID_10': applies_to.question_types has unknown tag 'TODO_tag'
  - sop 'TODO_ID_10': bad requires entry {'field': 'TODO', 'source': 'TODO'} (need field + source in ['current', 'daily', 'hourly'])
  - sop 'TODO_ID_10'.condition: a condition node must have exactly one key (compare, window_agg, score, all, any, not)
  - sop 'TODO_ID_10': advice placeholder {placeholders} is not produced by the condition (available: [])

## L1 [custom] - NOT RUN

- **What it checks:** THE 11TH-SOP TEST on the real SOP file - append a new SOP (new id, new required field, new activity tag) to a temp copy with no Python change.
- **Pass looks like:** The new id is matched and cited, the snapshot value is shown, the new field is requested from the API, and the unmodified file does not cite it.
- **Details:**
  - SOP file invalid, fix it first: Invalid SOP file:
  - meta.disclose_unknown_from must be one of severities ['TODO_lowest', 'TODO_middle', 'TODO_highest']
  - vocabulary.time_words.TODO_time_tag.window.start must be a whole hour 'HH:00' (end may be '24:00')
  - vocabulary.time_words.TODO_time_tag.window.end must be a whole hour 'HH:00' (end may be '24:00')
  - sop 'TODO_ID_01': id does not match meta.id_pattern 'TODO regex every SOP id must fully match, e.g. a fixed prefix; the verifier treats any text matching it as an SOP id'
  - sop 'TODO_ID_01': severity 'TODO' not in meta.severities
  - sop 'TODO_ID_01': applies_to.activities has unknown tag 'TODO_tag'
  - sop 'TODO_ID_01': applies_to.groups has unknown tag 'TODO_tag'
  - sop 'TODO_ID_01': applies_to.question_types has unknown tag 'TODO_tag'
  - sop 'TODO_ID_01': bad requires entry {'field': 'TODO', 'source': 'TODO'} (need field + source in ['current', 'daily', 'hourly'])
  - sop 'TODO_ID_01'.condition: a condition node must have exactly one key (compare, window_agg, score, all, any, not)
  - sop 'TODO_ID_01': advice placeholder {placeholders} is not produced by the condition (available: [])
  - sop 'TODO_ID_02': id does not match meta.id_pattern 'TODO regex every SOP id must fully match, e.g. a fixed prefix; the verifier treats any text matching it as an SOP id'
  - sop 'TODO_ID_02': severity 'TODO' not in meta.severities
  - sop 'TODO_ID_02': applies_to.activities has unknown tag 'TODO_tag'
  - sop 'TODO_ID_02': applies_to.groups has unknown tag 'TODO_tag'
  - sop 'TODO_ID_02': applies_to.question_types has unknown tag 'TODO_tag'
  - sop 'TODO_ID_02': bad requires entry {'field': 'TODO', 'source': 'TODO'} (need field + source in ['current', 'daily', 'hourly'])
  - sop 'TODO_ID_02'.condition: a condition node must have exactly one key (compare, window_agg, score, all, any, not)
  - sop 'TODO_ID_02': advice placeholder {placeholders} is not produced by the condition (available: [])
  - sop 'TODO_ID_03': id does not match meta.id_pattern 'TODO regex every SOP id must fully match, e.g. a fixed prefix; the verifier treats any text matching it as an SOP id'
  - sop 'TODO_ID_03': severity 'TODO' not in meta.severities
  - sop 'TODO_ID_03': applies_to.activities has unknown tag 'TODO_tag'
  - sop 'TODO_ID_03': applies_to.groups has unknown tag 'TODO_tag'
  - sop 'TODO_ID_03': applies_to.question_types has unknown tag 'TODO_tag'
  - sop 'TODO_ID_03': bad requires entry {'field': 'TODO', 'source': 'TODO'} (need field + source in ['current', 'daily', 'hourly'])
  - sop 'TODO_ID_03'.condition: a condition node must have exactly one key (compare, window_agg, score, all, any, not)
  - sop 'TODO_ID_03': advice placeholder {placeholders} is not produced by the condition (available: [])
  - sop 'TODO_ID_04': id does not match meta.id_pattern 'TODO regex every SOP id must fully match, e.g. a fixed prefix; the verifier treats any text matching it as an SOP id'
  - sop 'TODO_ID_04': severity 'TODO' not in meta.severities
  - sop 'TODO_ID_04': applies_to.activities has unknown tag 'TODO_tag'
  - sop 'TODO_ID_04': applies_to.groups has unknown tag 'TODO_tag'
  - sop 'TODO_ID_04': applies_to.question_types has unknown tag 'TODO_tag'
  - sop 'TODO_ID_04': bad requires entry {'field': 'TODO', 'source': 'TODO'} (need field + source in ['current', 'daily', 'hourly'])
  - sop 'TODO_ID_04'.condition: a condition node must have exactly one key (compare, window_agg, score, all, any, not)
  - sop 'TODO_ID_04': advice placeholder {placeholders} is not produced by the condition (available: [])
  - sop 'TODO_ID_05': id does not match meta.id_pattern 'TODO regex every SOP id must fully match, e.g. a fixed prefix; the verifier treats any text matching it as an SOP id'
  - sop 'TODO_ID_05': severity 'TODO' not in meta.severities
  - sop 'TODO_ID_05': applies_to.activities has unknown tag 'TODO_tag'
  - sop 'TODO_ID_05': applies_to.groups has unknown tag 'TODO_tag'
  - sop 'TODO_ID_05': applies_to.question_types has unknown tag 'TODO_tag'
  - sop 'TODO_ID_05': bad requires entry {'field': 'TODO', 'source': 'TODO'} (need field + source in ['current', 'daily', 'hourly'])
  - sop 'TODO_ID_05'.condition: a condition node must have exactly one key (compare, window_agg, score, all, any, not)
  - sop 'TODO_ID_05': advice placeholder {placeholders} is not produced by the condition (available: [])
  - sop 'TODO_ID_06': id does not match meta.id_pattern 'TODO regex every SOP id must fully match, e.g. a fixed prefix; the verifier treats any text matching it as an SOP id'
  - sop 'TODO_ID_06': severity 'TODO' not in meta.severities
  - sop 'TODO_ID_06': applies_to.activities has unknown tag 'TODO_tag'
  - sop 'TODO_ID_06': applies_to.groups has unknown tag 'TODO_tag'
  - sop 'TODO_ID_06': applies_to.question_types has unknown tag 'TODO_tag'
  - sop 'TODO_ID_06': bad requires entry {'field': 'TODO', 'source': 'TODO'} (need field + source in ['current', 'daily', 'hourly'])
  - sop 'TODO_ID_06'.condition: a condition node must have exactly one key (compare, window_agg, score, all, any, not)
  - sop 'TODO_ID_06': advice placeholder {placeholders} is not produced by the condition (available: [])
  - sop 'TODO_ID_07': id does not match meta.id_pattern 'TODO regex every SOP id must fully match, e.g. a fixed prefix; the verifier treats any text matching it as an SOP id'
  - sop 'TODO_ID_07': severity 'TODO' not in meta.severities
  - sop 'TODO_ID_07': applies_to.activities has unknown tag 'TODO_tag'
  - sop 'TODO_ID_07': applies_to.groups has unknown tag 'TODO_tag'
  - sop 'TODO_ID_07': applies_to.question_types has unknown tag 'TODO_tag'
  - sop 'TODO_ID_07': bad requires entry {'field': 'TODO', 'source': 'TODO'} (need field + source in ['current', 'daily', 'hourly'])
  - sop 'TODO_ID_07'.condition: a condition node must have exactly one key (compare, window_agg, score, all, any, not)
  - sop 'TODO_ID_07': advice placeholder {placeholders} is not produced by the condition (available: [])
  - sop 'TODO_ID_08': id does not match meta.id_pattern 'TODO regex every SOP id must fully match, e.g. a fixed prefix; the verifier treats any text matching it as an SOP id'
  - sop 'TODO_ID_08': severity 'TODO' not in meta.severities
  - sop 'TODO_ID_08': applies_to.activities has unknown tag 'TODO_tag'
  - sop 'TODO_ID_08': applies_to.groups has unknown tag 'TODO_tag'
  - sop 'TODO_ID_08': applies_to.question_types has unknown tag 'TODO_tag'
  - sop 'TODO_ID_08': bad requires entry {'field': 'TODO', 'source': 'TODO'} (need field + source in ['current', 'daily', 'hourly'])
  - sop 'TODO_ID_08'.condition: a condition node must have exactly one key (compare, window_agg, score, all, any, not)
  - sop 'TODO_ID_08': advice placeholder {placeholders} is not produced by the condition (available: [])
  - sop 'TODO_ID_09': id does not match meta.id_pattern 'TODO regex every SOP id must fully match, e.g. a fixed prefix; the verifier treats any text matching it as an SOP id'
  - sop 'TODO_ID_09': severity 'TODO' not in meta.severities
  - sop 'TODO_ID_09': applies_to.activities has unknown tag 'TODO_tag'
  - sop 'TODO_ID_09': applies_to.groups has unknown tag 'TODO_tag'
  - sop 'TODO_ID_09': applies_to.question_types has unknown tag 'TODO_tag'
  - sop 'TODO_ID_09': bad requires entry {'field': 'TODO', 'source': 'TODO'} (need field + source in ['current', 'daily', 'hourly'])
  - sop 'TODO_ID_09'.condition: a condition node must have exactly one key (compare, window_agg, score, all, any, not)
  - sop 'TODO_ID_09': advice placeholder {placeholders} is not produced by the condition (available: [])
  - sop 'TODO_ID_10': id does not match meta.id_pattern 'TODO regex every SOP id must fully match, e.g. a fixed prefix; the verifier treats any text matching it as an SOP id'
  - sop 'TODO_ID_10': severity 'TODO' not in meta.severities
  - sop 'TODO_ID_10': applies_to.activities has unknown tag 'TODO_tag'
  - sop 'TODO_ID_10': applies_to.groups has unknown tag 'TODO_tag'
  - sop 'TODO_ID_10': applies_to.question_types has unknown tag 'TODO_tag'
  - sop 'TODO_ID_10': bad requires entry {'field': 'TODO', 'source': 'TODO'} (need field + source in ['current', 'daily', 'hourly'])
  - sop 'TODO_ID_10'.condition: a condition node must have exactly one key (compare, window_agg, score, all, any, not)
  - sop 'TODO_ID_10': advice placeholder {placeholders} is not produced by the condition (available: [])

## S2 [live] - NOT RUN

- **What it checks:** Genuinely severe LIVE weather: answer cites the real numbers from this request's API snapshot (date-dependent).
- **Pass looks like:** A configured severe SOP is TRUE for the first qualifying candidate city; the reply cites it and every number is from that snapshot. SKIPPED (never pass) if none is active.
- **Details:**
  - not yet configured: live_cases.yaml has no severe_sop_ids (needs your real SOP file)
