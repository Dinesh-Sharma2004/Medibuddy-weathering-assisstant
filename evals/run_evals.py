"""Eval runner.   python evals/run_evals.py --suite fixture|user [--mode engine|e2e|all] [--runs N] [--case ID]

engine mode: hand-built intent (ScriptedParser) + fixture weather, no LLM, deterministic, runs once.
llm mode   : the real LLM parses and composes; fixture (or live) weather. Runs N times; a case passes only if
             ALL N runs pass (2/3 is FAIL and is reported as 2/3). Needs OPENAI_API_KEY and OPENAI_MODEL.
Writes evals/RESULTS.md (fixture) or evals/RESULTS_user.md (user). Never edits cases to make them pass.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from weather_advisor import conditions  # noqa: E402
from weather_advisor.graph import ask as graph_ask, build_graph  # noqa: E402
from weather_advisor.sops import load_sops  # noqa: E402
from weather_advisor.verify import _id_tokens, _numbers  # noqa: E402
from weather_advisor.weather import FaultInjectingClient, FixtureClient, OpenMeteoClient, build_snapshot  # noqa: E402
import custom_checks  # noqa: E402

EVALS = Path(__file__).parent
WEATHER_DIR = EVALS / "fixtures" / "weather"
GEOCODE = json.loads((EVALS / "fixtures" / "geocode.json").read_text())
SUITES = {
    "fixture": {"sops": ROOT / "tests" / "fixtures" / "sops_fixture.yaml", "cases": EVALS / "cases_fixture.yaml",
                "out": EVALS / "RESULTS.md"},
    "user": {"sops": ROOT / "sops" / "sops.yaml", "cases": EVALS / "cases_user.yaml",
             "out": EVALS / "RESULTS_user.md"},
}
STOP = set("this that with from have what will would should could about there their your into than then them "
           "when which while where does just like".split())


class ScriptedParser:
    def __init__(self, intents):
        self.intents = list(intents)

    def __call__(self, text, policy, session):
        full = {"in_scope": True, "asks_for_explanation": False, "location_text": None, "activities": [],
                "groups": [], "question_types": [], "time_reference": None}
        return {**full, **self.intents.pop(0)}


class Spy:
    def __init__(self, inner=None):
        self.inner, self.calls = inner, []

    def __call__(self, payload):
        self.calls.append(payload)
        return self.inner(payload) if self.inner else ""


def weather_payload(name):
    return json.loads((WEATHER_DIR / f"{name}.json").read_text())


def make_client(weather, fault=None):
    c = FixtureClient(weather_payload(weather), GEOCODE)
    return FaultInjectingClient(c, fault) if fault else c


def get_path(d, path):
    for part in path.split("."):
        if not isinstance(d, dict) or part not in d:
            return KeyError
        d = d[part]
    return d


# ---------- context shared with custom checks ----------
def build_engine(sop_file, weather, fault=None, composer=None, intents=()):
    return build_graph(sop_file, make_client(weather, fault), ScriptedParser(intents), composer=composer)


def creds_missing():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    miss = [k for k in ("OPENAI_API_KEY", "OPENAI_MODEL") if not os.environ.get(k)]
    return f"{' and '.join(miss)} not set (see .env.example)" if miss else None


# ---------- assertions ----------
def grounded_numbers_ok(result, policy):
    t, reply = result["trace"], result["reply"]
    allowed: set[float] = set()
    texts = [t.get("chosen_place", {}).get("label", ""), t.get("weather_snapshot", {}).get("now_local", "")]
    by_id = {s.id: s for s in policy.sops}
    for e in t.get("sop_evaluations", []):
        if e["effective"] == "TRUE":
            allowed |= {float(conditions.fmt_number(v)) for v in e["evidence"].values()
                        if isinstance(v, (int, float)) and not isinstance(v, bool)}
            texts.append(re.sub(r"\{\w+\}", " ", by_id[e["id"]].advice))
        if e["id"] in t.get("disclosed_unknown_sops", []):
            texts.append(by_id[e["id"]].title)
    strip = _id_tokens(reply, policy) | _id_tokens(" ".join(texts), policy)
    for x in texts:
        allowed |= set(_numbers(x, strip))
    bad = sorted({n for n in _numbers(reply, strip) if n not in allowed})
    return not bad, bad


def check_turn(expect, result, ctx, prev, clean, weather_name, spy) -> list[str]:
    fails = []
    t, reply = result["trace"], result["reply"]
    if "branch" in expect and result["branch"] != expect["branch"]:
        fails.append(f"branch: got {result['branch']!r}, want {expect['branch']!r}")
    if "branch_in" in expect and result["branch"] not in expect["branch_in"]:
        fails.append(f"branch {result['branch']!r} not in {expect['branch_in']}")
    if "reply_source" in expect and result["reply_source"] != expect["reply_source"]:
        fails.append(f"reply_source: got {result['reply_source']!r}, want {expect['reply_source']!r}")
    for path, want in (expect.get("trace") or {}).items():
        got = get_path(t, path)
        if got is KeyError:
            got = "<absent>"
        if got != want and not (want is None and got == "<absent>"):
            fails.append(f"trace.{path}: got {got!r}, want {want!r}")
    for key in expect.get("trace_absent") or []:
        if key in t:
            fails.append(f"trace should not contain {key!r}")
    ev = {e["id"]: e for e in t.get("sop_evaluations", [])}
    for sid, want in (expect.get("evaluations") or {}).items():
        got = ev.get(sid, {}).get("effective")
        if got != want:
            fails.append(f"evaluation {sid}: got {got}, want {want}")
    for sid, names in (expect.get("evidence_from_snapshot") or {}).items():
        snap = weather_payload(weather_name)
        for name, path in names.items():
            want = get_path(snap, path)
            got = ev.get(sid, {}).get("evidence", {}).get(name)
            if got != want:
                fails.append(f"evidence {sid}.{name}: got {got!r}, snapshot {path} = {want!r}")
    for key in expect.get("same_as_previous") or []:
        if prev is None or t.get(key) != prev["trace"].get(key):
            fails.append(f"{key} differs from the previous turn: {t.get(key)!r} vs {prev and prev['trace'].get(key)!r}")
    for key in expect.get("same_as_clean") or []:
        if clean is None or t.get(key) != clean["trace"].get(key):
            fails.append(f"{key} differs from the clean question: {t.get(key)!r} vs {clean and clean['trace'].get(key)!r}")
    if "composer_calls" in expect and len(spy.calls) != expect["composer_calls"]:
        fails.append(f"compose calls: got {len(spy.calls)}, want {expect['composer_calls']}")
    if expect.get("no_digits") and re.search(r"\d", reply):
        fails.append(f"reply contains digits: {reply!r}")
    for s in expect.get("reply_contains") or []:
        if str(s).lower() not in reply.lower():
            fails.append(f"reply lacks {s!r}")
    for s in expect.get("reply_not_contains") or []:
        if str(s).lower() in reply.lower():
            fails.append(f"reply contains forbidden {s!r}")
    if expect.get("reply_lacks_numbers"):
        found = set(_numbers(reply, _id_tokens(reply, ctx.policy)))
        for n in expect["reply_lacks_numbers"]:
            if float(n) in found:
                fails.append(f"reply states the planted number {n}")
    if expect.get("reply_numbers_grounded"):
        ok, bad = grounded_numbers_ok(result, ctx.policy)
        if not ok:
            fails.append(f"numbers in reply not grounded in this request's snapshot/advice: {bad}")
    if fails and t.get("failure_reason"):
        fails.append(f"(trace.failure_reason: {str(t['failure_reason'])[:300]})")
    if fails and clean is not None and clean["branch"] != "compose":
        fails.append(f"(the clean-question run itself ended in branch {clean['branch']!r}: "
                     f"{str(clean['trace'].get('failure_reason', ''))[:300]})")
    return fails


# ---------- running a case ----------
def run_case_once(case, mode, ctx):
    try:
        return _run_case_once(case, mode, ctx)
    except Exception as e:   # a crash is a failure of the system under test, not of the runner
        return [f"crashed: {type(e).__name__}: {e}"], []


def _run_case_once(case, mode, ctx):
    spy = Spy(ctx.llm_composer if mode == "llm" else None)
    turns = case["turns"]
    weather = case.get("weather", "calm")
    client = make_client(weather, case.get("fault"))
    if mode == "engine":
        missing = [i for i, tn in enumerate(turns) if "intent" not in tn]
        if missing:
            return ["engine mode needs an `intent` on every turn"], []
        parser = ScriptedParser([tn["intent"] for tn in turns])
    else:
        parser = ctx.llm_parser
    app = build_graph(ctx.sop_file, client, parser, composer=spy)
    thread, prev, fails, results = f"{case['id']}-{id(spy)}", None, [], []
    for i, tn in enumerate(turns, 1):
        w = tn.get("weather", weather)
        inner = client.inner if hasattr(client, "inner") else client
        inner.payload = weather_payload(w)
        clean = None
        if tn.get("clean_say") and mode == "llm":
            capp = build_graph(ctx.sop_file, make_client(w, case.get("fault")), ctx.llm_parser, composer=Spy(ctx.llm_composer))
            clean = graph_ask(capp, thread + "-clean", tn["clean_say"])
        text = tn.get("say", "(scripted intent)") if mode == "llm" else tn.get("say", "(scripted intent)")
        result = graph_ask(app, thread, text)
        results.append(result)
        for f in check_turn(tn.get("expect") or {}, result, ctx, prev, clean, w, spy):
            fails.append(f"turn {i}: {f}")
        prev = result
    return fails, results


def lint_paraphrase(case, policy):
    warns = []
    by_id = {s.id: s for s in policy.sops}
    for tn in case["turns"]:
        say = tn.get("say", "")
        words = {w for w in re.findall(r"[a-z]{4,}", say.lower()) if w not in STOP}
        for sid in case.get("targets", []):
            s = by_id.get(sid)
            if not s:
                warns.append(f"target {sid} not in SOP file")
                continue
            vocab = set(re.findall(r"[a-z]{4,}", s.title.lower()))
            for dim in ("activities", "groups", "question_types"):
                if s.applies_to[dim] != "any":
                    for tag in s.applies_to[dim]:
                        vocab |= set(re.findall(r"[a-z]{4,}", tag.lower().replace("_", " ")))
            shared = sorted(words & vocab - {"dummy"})
            if shared:
                warns.append(f"paraphrase for {sid} shares words with its title/tags: {shared}")
    return warns


# ---------- live S2 ----------
def run_live(ctx, args):
    cfg = yaml.safe_load((EVALS / "live_cases.yaml").read_text())
    ids = cfg.get("severe_sop_ids") or []
    if not ids:
        return "NOT RUN", ["not yet configured: live_cases.yaml has no severe_sop_ids (needs your real SOP file)"]
    miss = creds_missing()
    if miss:
        return "NOT RUN", [miss]
    try:
        policy = load_sops(ctx.sop_file)
    except Exception as e:
        return "FAIL", [f"SOP file invalid: {e}"]
    by_id = {s.id: s for s in policy.sops}
    unknown_ids = [i for i in ids if i not in by_id]
    if unknown_ids:
        return "FAIL", [f"severe_sop_ids not in SOP file: {unknown_ids}"]
    client, log, chosen = OpenMeteoClient(), [], None
    for city in cfg["candidates"]:
        try:
            cand = client.geocode(city)[0]
            fields = policy.required_fields()
            snap = build_snapshot(client.forecast(cand["latitude"], cand["longitude"], fields), fields)
            ectx = conditions.EvalContext(snap, policy.vocabulary, policy.meta["default_time_reference"])
            res = {i: conditions.evaluate(by_id[i].condition, ectx).value for i in ids}
        except Exception as e:
            log.append(f"{city}: error {e}")
            continue
        log.append(f"{city}: {res}")
        if "TRUE" in res.values():
            chosen = city
            break
    if not chosen:
        return "SKIPPED", ["no candidate city currently satisfies a configured severe SOP (date-dependent case)"] + log
    app = build_graph(ctx.sop_file, client, ctx.llm_parser, composer=Spy(ctx.llm_composer))
    r = graph_ask(app, "live", cfg["question"].format(city=chosen))
    t = r["trace"]
    fails = []
    if not set(t.get("matched_sops", [])) & set(ids):
        fails.append(f"full run matched {t.get('matched_sops')}, none of the severe SOPs {ids} (weather may have changed between fetches)")
    ok, bad = grounded_numbers_ok(r, policy)
    if not ok:
        fails.append(f"numbers not from this request's snapshot: {bad}")
    if not any(i in r["reply"] for i in ids):
        fails.append("reply does not cite a severe SOP id")
    return ("FAIL" if fails else "PASS"), [f"city used: {chosen}", *log, f"reply_source={r['reply_source']}", *fails]


# ---------- main ----------
def referenced_ids(cases, policy_ids):
    refs = set()
    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ("trace", "evaluations", "evidence_from_snapshot", "reply_contains", "targets", "covers"):
                    refs.update(i for i in policy_ids if i in json.dumps(v))
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(cases)
    return refs


def git_sha():
    try:
        return subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                                       stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return "no commits yet"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", choices=SUITES, default="fixture")
    ap.add_argument("--mode", choices=["engine", "e2e", "all"], default="all")
    ap.add_argument("--runs", type=int, default=3, help="repeats per LLM-dependent case (all must pass)")
    ap.add_argument("--case", help="only this case id")
    args = ap.parse_args()
    suite = SUITES[args.suite]
    cases = yaml.safe_load(suite["cases"].read_text())["cases"]
    try:
        policy = load_sops(suite["sops"])
        policy_err = None
    except Exception as e:
        policy, policy_err = None, str(e)

    miss = creds_missing()
    llm_parser = llm_composer = None
    if not miss and args.mode in ("e2e", "all"):
        from weather_advisor.llm import make_composer, make_llm, make_parser
        llm = make_llm()
        llm_parser, llm_composer = make_parser(llm), make_composer(llm)
    ctx = SimpleNamespace(sop_file=suite["sops"], policy=policy, llm_parser=llm_parser, llm_composer=llm_composer,
                          build_engine=build_engine, ask=graph_ask,
                          referenced_ids=referenced_ids(cases, [s.id for s in policy.sops]) if policy else set())
    rows = []
    for case in cases:
        if args.case and case["id"] != args.case:
            continue
        tier = case["tier"]
        modes = {"both": ["engine", "llm"], "engine": ["engine"], "e2e": ["llm"], "custom": ["custom"]}[tier]
        for mode in modes:
            row = {"id": case["id"], "mode": mode, "what": case["what_it_checks"], "pass": case["pass_criteria"],
                   "status": None, "detail": [], "warn": []}
            rows.append(row)
            if policy_err and args.suite == "user" and case.get("custom") != "no_policy_in_source":
                row.update(status="NOT RUN", detail=[f"SOP file invalid, fix it first: {policy_err}"])
                continue
            if mode == "engine" and args.mode == "e2e" or mode == "llm" and args.mode == "engine":
                row.update(status="NOT RUN", detail=[f"--mode {args.mode}"])
                continue
            if mode == "custom":
                fn = getattr(custom_checks, case["custom"])
                ctx.params = case.get("params") or {}
                try:
                    ok, lines = fn(ctx)
                except Exception as e:
                    ok, lines = False, [f"crashed: {type(e).__name__}: {e}"]
                row.update(status="NOT RUN" if ok is None else "PASS" if ok else "FAIL", detail=lines)
                continue
            if mode == "llm":
                row["warn"] = lint_paraphrase(case, policy) if case.get("targets") and policy else []
                if miss or llm_parser is None:
                    row.update(status="NOT RUN", detail=[miss or "LLM not configured"])
                    continue
                passed, runs, infra, real = 0, args.runs, 0, 0
                for k in range(runs):
                    fails, _ = run_case_once(case, mode, ctx)
                    passed += not fails
                    if fails:
                        row["detail"].append(f"run {k + 1}: " + " | ".join(fails))
                        # a provider rate limit says nothing about the system under test
                        if re.search(r"Error code: 429|Rate limit reached", " ".join(fails)):
                            infra += 1
                        else:
                            real += 1
                status = "PASS" if passed == runs else "INFRA ERROR" if infra and not real else "FAIL"
                row.update(status=status, k=f"{passed}/{runs}")
                if status == "INFRA ERROR":
                    row["detail"].insert(0, f"{infra} run(s) hit the LLM provider's rate limit (HTTP 429); not a verdict on the system. Re-run after the quota resets.")
                continue
            fails, _ = run_case_once(case, "engine", ctx)
            row.update(status="FAIL" if fails else "PASS", detail=fails)
    if args.suite == "user" and not args.case:
        status, lines = run_live(ctx, args)
        rows.append({"id": "S2", "mode": "live", "status": status, "detail": lines, "warn": [],
                     "what": "Genuinely severe LIVE weather: answer cites the real numbers from this request's API snapshot (date-dependent).",
                     "pass": "A configured severe SOP is TRUE for the first qualifying candidate city; the reply cites it and every number is from that snapshot. SKIPPED (never pass) if none is active."})
    if args.case:
        print("(--case given: results file not written)")
    else:
        if args.mode != "all":   # a partial run must never overwrite the full results file
            suite = {**suite, "out": suite["out"].with_name(suite["out"].stem + f"_{args.mode}_only.md")}
        write_results(rows, args, suite)
    for r in rows:
        print(f"{r['status']:8} {r['id']:5} [{r['mode']}] {r.get('k', '')}")
    bad = [r for r in rows if r["status"] == "FAIL"]
    print(f"\n{sum(r['status']=='PASS' for r in rows)} pass, {len(bad)} fail, "
          f"{sum(r['status']=='INFRA ERROR' for r in rows)} infra error, {sum(r['status']=='NOT RUN' for r in rows)} not run, {sum(r['status']=='SKIPPED' for r in rows)} skipped"
          f"{'' if args.case else ' -> ' + str(suite['out'].relative_to(ROOT))}")
    sys.exit(1 if bad else 0)


def write_results(rows, args, suite):
    counts = {s: sum(r["status"] == s for r in rows) for s in ("PASS", "FAIL", "INFRA ERROR", "NOT RUN", "SKIPPED")}
    L = [f"# Eval results ({args.suite} suite)", "",
         f"- Date: {datetime.datetime.now().isoformat(timespec='seconds')}",
         f"- Model: {os.environ.get('OPENAI_MODEL') or 'n/a (no LLM configured for this run)'}",
         f"- Git SHA: {git_sha()}",
         f"- Mode: {args.mode}; LLM runs per case: {args.runs} (a case passes only if all runs pass)",
         f"- Summary: {counts['PASS']} PASS, {counts['FAIL']} FAIL, {counts['INFRA ERROR']} INFRA ERROR, {counts['NOT RUN']} NOT RUN, {counts['SKIPPED']} SKIPPED", "",
         "| Case | Mode | Result |", "|---|---|---|"]
    for r in rows:
        L.append(f"| {r['id']} | {r['mode']} | {r['status']}{' ' + r['k'] if r.get('k') else ''} |")
    L.append("")
    for r in rows:
        L += [f"## {r['id']} [{r['mode']}] - {r['status']}{' ' + r['k'] if r.get('k') else ''}", "",
              f"- **What it checks:** {r['what']}", f"- **Pass looks like:** {r['pass']}"]
        for w in r["warn"]:
            L.append(f"- **LINT WARNING:** {w}")
        if r["detail"]:
            L.append("- **Details:**")
            L += [f"  - {d}" for d in r["detail"]]
        L.append("")
    suite["out"].write_text("\n".join(L))


if __name__ == "__main__":
    main()
