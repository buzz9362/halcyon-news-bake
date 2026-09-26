"""Sep 26 2026 (WK): are the NEWEST stories of every live feed actually voiced and listed?

The Sep 25 lesson: runs 36143270740 and 36174562701 hid 7,272 and 6,183 failed gTTS synths behind
the manifest carry-forward. generatedAtMs stayed fresh (every pass rewrites the manifest) and the car
kept playing day-old news. This check does not trust generatedAtMs. Per manifest in bake.MANIFESTS it
GETs the live feed_url and the served manifest, takes the newest K feed stories that bake.py itself
would voice (bake.sanitize_article + text_for + apply_phonetics >= MIN_TEXT_LEN, dedup by id, newest
first by bake._pub_ms: the rule plan_manifest applies, guarded against drift below), and reports the
share of them that are BOTH listed in the manifest AND have a served MP3 (HEAD 200), the same share
over the newest K "settled" stories (published GRACE_H or more ago), the newest story's age, the
newest voiced story's age and the lag between them.

  python tools/fresh_coverage_check.py                     # all 27 manifests, K=10
  python tools/fresh_coverage_check.py --gh                # plus the latest "Bake article MP3s" runs
  python tools/fresh_coverage_check.py --manifests kpop_en,tickerly_hi --k 5 --json out.json
  python tools/fresh_coverage_check.py --selftest          # positive controls only (offline)

--gh reads the latest completed runs of the workflow (gh run list / gh run view --log, repo
buzz9362/halcyon-news-bake) back to the latest completed LOOP run: passes, gTTS 429s, breaker state,
failed synths (bake FAILED and re-voice FAILED lines), STARVED manifests. An in-progress run is listed
(GitHub serves no log until a run completes). It also checks that the repo is still public: the repo
going private ran the Actions minutes out.

Exit 0 = no finding (WARNs allowed), 1 = a finding, 2 = the check is broken (a positive control
failed, bake's eligibility rule changed under this mirror) or nothing was read. A feed, manifest or
HEAD that times out or answers 5xx is UNREAD for this run, never a miss. Read-only: GETs public feeds,
manifests and MP3 heads, runs gh read commands; never writes R2.

FINDINGS (exit 1): a manifest whose newest voiced story is more than MAX_LAG_H behind its newest feed
story, or with nothing voiced at all; fleet newest share < FLOOR_FLEET_NEWEST; fleet settled share <
FLOOR_FLEET_SETTLED; --gh: repo private, failed synths > MAX_FAILED_SYNTH in the latest loop run, or
more than MAX_ZERO_PASS_SHARE of its passes baked nothing.
WARN (exit 0): one manifest's settled share < WARN_SETTLED. Under the gTTS budget bake_fresh voices
newest first, so a fast feed skips part of its 2-5 h old stories while its newest ones play.

BASELINE, measured Sep 26 2026 (bake 9f999e0; loop run 36234130328 started 09:53Z; gTTS was
throttling: the previous loop run 36230985595 opened the breaker in both completed passes and its
pass 2 baked nothing; repo public):
  10:00Z newest K=10, no grace: fleet 169/266 = 64%; per manifest 10% (circuitly_fr, tickerly_id,
         tickerly_de) to 100%; 97 misses, 94 of them under 2 h old (the pass cadence), 2.85 h, 7.22 h
         (tickerly_en: MP3 served, not listed) and 12.23 h (tickerly_pt) the rest.
  10:07Z settled (>= 2 h): fleet 208/256 = 81%; below 50%: tickerly_vi 10%, tickerly_de 20%,
         circuitly_de 40%, circuitly_it 40%, tickerly_id 40% (skipped 2-5 h old stories; newest ones
         voiced); bollywood_en has no settled story (all 60 feed items are 0.1-1.3 h old).
  10:14Z (tool as committed, --gh, exit 0): newest 234/267 = 88%, settled 230/256 = 90%, max lag 1.04 h;
         WARN tickerly_vi settled 10%, tickerly_de 20%; newest share 30% in tickerly_es and tickerly_fr.
  lag (newest feed story minus newest voiced): max 1.04 h (anime_en) in all three, 0 h in 15 of 27.
  --gh: latest loop run 36230985595: 3 passes (cancelled in pass 3 by the next dispatch), 251 baked,
         1 of 2 completed passes baked nothing, 6 gTTS 429s, breaker OPEN in both, 4 failed synths,
         16 manifests STARVED in pass 2. Sep 25 controls: 6,183 (36174562701) and 7,272 (36143270740)
         failed synths, 9 of 10 passes baked nothing.
  Wall time: about 2.5 min for 27 manifests (one request at a time), plus about 10 s for --gh.
"""
from __future__ import annotations

import argparse
import calendar
import contextlib
import gzip
import importlib.util
import inspect
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_BASE = "https://pub-fcb63a0a41b446ea825306ef86fc224f.r2.dev"
UA = {"User-Agent": "halcyon-news-bake fresh_coverage_check (read-only; one request at a time)"}
REPO = "buzz9362/halcyon-news-bake"
WORKFLOW = "Bake article MP3s"
STORE = os.environ.get("HALCYON_SOURCE_HEALTH") or os.path.join(
    os.path.dirname(ROOT), "App Market Submission", "_source_health")
GH_CONTROLS = os.path.join(STORE, "controls", "gh")

# ---------- floors (from the BASELINE above, with a margin) ----------
K_DEFAULT = 10
# A story younger than this is not "settled" yet (a pass runs every 30 min and takes up to ~20 min;
# the 429 breaker can defer a story by a pass).
GRACE_H = 2.0
# FINDING: newest feed story minus newest voiced story, per manifest. Baseline max 1.04 h; a loop gap
# (GitHub delivers the schedule every 96-383 min against a 300 min loop) can add about 1.5 h.
MAX_LAG_H = 3.0
# FINDING: share of the newest K eligible stories voiced AND listed, over all manifests read.
FLOOR_FLEET_NEWEST = 0.40      # baseline 64% (mid-pass) and 88%
# FINDING: the same share over the newest K settled stories.
FLOOR_FLEET_SETTLED = 0.60     # baseline 81% and 90%
# WARN only: one manifest's settled share (baseline min 10%).
WARN_SETTLED = 0.50
# --gh FINDING: failed synths in the latest completed loop run (baseline 4; Sep 25: 6,183 and 7,272).
MAX_FAILED_SYNTH = 300
# --gh FINDING: share of passes that baked nothing, once a run has this many passes (Sep 25: 9 of 10).
MAX_ZERO_PASS_SHARE = 0.75
MIN_PASSES_FOR_SHARE = 4

# The per-article rule of bake.plan_manifest this tool mirrors. If bake.py changes it, the mirror
# is stale and the check says so (exit 2) instead of measuring the wrong thing.
PLAN_RULE_FRAGMENTS = (
    "sanitize_article(a)",
    "if not aid or aid in seen",
    "apply_phonetics(text_for(article), phon)",
    "len(text) < MIN_TEXT_LEN",
)


def load_bake():
    for k, v in (("R2_ACCESS_KEY_ID", "x"), ("R2_SECRET_ACCESS_KEY", "x"), ("R2_ENDPOINT_URL", "https://example.invalid")):
        os.environ.setdefault(k, v)
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        spec = importlib.util.spec_from_file_location("bake", os.path.join(ROOT, "bake.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
    finally:
        os.chdir(cwd)
    return m


def rule_drift(bake) -> list[str]:
    src = inspect.getsource(bake.plan_manifest)
    return [f for f in PLAN_RULE_FRAGMENTS if f not in src]


def bake_eligible(bake, m: dict, raw_items: list) -> list[dict]:
    """Feed items bake.plan_manifest would list or voice, newest first (its own functions)."""
    out, seen = [], set()
    cwd = os.getcwd()
    os.chdir(ROOT)   # load_phonetics reads phonetics/<table>.csv relative to the repo
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            for raw in raw_items:
                if not isinstance(raw, dict):
                    continue
                a = bake.sanitize_article(raw)
                aid = a.get("id")
                if not aid or aid in seen:
                    continue
                seen.add(aid)
                text = bake.apply_phonetics(bake.text_for(a), m["phonetics"])
                if len(text) < bake.MIN_TEXT_LEN:
                    continue
                out.append(a)
    finally:
        os.chdir(cwd)
    out.sort(key=bake._pub_ms, reverse=True)
    return out


# ---------- HTTP (one request at a time) ----------

def get_json(url: str, tries: int = 2):
    last = None
    for n in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:   # transient: retried once, then UNREAD (never a miss)
            last = e
            time.sleep(2)
    raise last


def head_status(url: str, tries: int = 2) -> bool | None:
    """True = 200, False = 404/403 (not there), None = transient (unknown)."""
    for n in range(tries):
        try:
            req = urllib.request.Request(url, method="HEAD", headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status == 200
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return False
        except Exception:
            pass
        time.sleep(1.5)
    return None


# ---------- the measure (pure; the selftest and the live run share it) ----------

def evaluate(bake, name: str, eligible: list[dict], manifest_ids: set, served, now_ms: int, k: int) -> dict:
    """One manifest. served(aid) -> True/False/None (None = transient: unknown, never a miss).
    newest  = the newest k eligible feed stories (the top of the car's list);
    settled = the newest k eligible stories published at least GRACE_H ago."""
    grace_ms = GRACE_H * 3.6e6
    newest = eligible[:k]
    settled = [a for a in eligible if now_ms - bake._pub_ms(a) >= grace_ms][:k]
    rows = {}
    for a in newest + settled:
        aid = a["id"]
        if aid not in rows:
            rows[aid] = {"id": aid, "pub_ms": bake._pub_ms(a), "listed": aid in manifest_ids, "served": served(aid)}

    # A row is voiced (listed + 200), missing (not listed, or 404) or unknown (listed, HEAD transient).
    def known(r):
        return (not r["listed"]) or r["served"] is not None

    def share(items):
        kn = [rows[a["id"]] for a in items if known(rows[a["id"]])]
        ok = sum(1 for r in kn if r["listed"] and r["served"])
        return ok, len(kn), (ok / len(kn) if kn else None)

    n_ok, n_known, n_cov = share(newest)
    s_ok, s_known, s_cov = share(settled)
    newest_feed = max((r["pub_ms"] for r in rows.values() if known(r)), default=0)
    voiced = [r["pub_ms"] for r in rows.values() if r["listed"] and r["served"]]
    newest_voiced = max(voiced, default=0)
    lag_h = max(0.0, (newest_feed - newest_voiced) / 3.6e6) if (newest_feed and newest_voiced) else None
    findings, warns = [], []
    all_known = all(known(r) for r in rows.values())
    if rows and not voiced and all_known:
        findings.append(f"none of the newest {len(rows)} eligible feed stories is voiced and listed")
    elif lag_h is not None and lag_h > MAX_LAG_H:
        findings.append(f"newest voiced story is {lag_h:.1f} h behind the newest feed story (> {MAX_LAG_H} h)")
    if s_cov is not None and s_cov < WARN_SETTLED:
        warns.append(f"settled {s_ok}/{s_known} = {s_cov:.0%} < {WARN_SETTLED:.0%}: stories older than "
                     f"{GRACE_H:g} h were skipped (gTTS budget, newest first)")
    return {
        "manifest": name,
        "newest": {"k": len(newest), "known": n_known, "ok": n_ok, "coverage": n_cov},
        "settled": {"k": len(settled), "known": s_known, "ok": s_ok, "coverage": s_cov},
        "newest_feed_age_h": round((now_ms - newest_feed) / 3.6e6, 2) if newest_feed else None,
        "newest_voiced_age_h": round((now_ms - newest_voiced) / 3.6e6, 2) if newest_voiced else None,
        "lag_h": round(lag_h, 2) if lag_h is not None else None,
        "missing": sorted((r for r in rows.values() if known(r) and not (r["listed"] and r["served"])),
                          key=lambda r: -r["pub_ms"]),
        "unknown": [r["id"] for r in rows.values() if not known(r)],
        "findings": findings, "warns": warns,
    }


def fleet(rows: list[dict]) -> dict:
    out = {}
    for part in ("newest", "settled"):
        ok = sum(r[part]["ok"] for r in rows)
        known = sum(r[part]["known"] for r in rows)
        out[part] = {"ok": ok, "known": known, "coverage": ok / known if known else None}
    return out


def fleet_findings(fl: dict) -> list[str]:
    f = []
    for part, floor in (("newest", FLOOR_FLEET_NEWEST), ("settled", FLOOR_FLEET_SETTLED)):
        c = fl[part]
        if c["coverage"] is not None and c["coverage"] < floor:
            f.append(f"fleet {part} coverage {c['ok']}/{c['known']} = {c['coverage']:.0%} < floor {floor:.0%}")
    return f


# ---------- --gh ----------

RE_PASS = re.compile(r"##\[group\]bake pass (\d+) at")
RE_PASS_FAILED = re.compile(r"\bpass \d+ FAILED, continuing")
RE_SUMMARY = re.compile(r"Summary: (\d+) baked, (\d+) already-cached, ([\d.]+)s"
                        r"(?:, gTTS 429s=(\d+), synth attempts=(\d+), breaker=(OPEN|closed))?")
RE_RETEXT_SUMMARY = re.compile(r"Summary: retext_ids voiced (\d+)/(\d+);.*gTTS 429s=(\d+), synth attempts=(\d+), "
                               r"breaker=(OPEN|closed)")
RE_SYNTH_FAILED = re.compile(r"\b(?:bake|re-voice) (?:FAILED|failed)\b")
RE_STARVED = re.compile(r"\[([a-z]+_[a-z]+)\] STARVED: (\d+) fresh stories")
RE_LOOP_END = re.compile(r"bake passes=(\d+) succeeded=(\d+)")


def gh(args: list[str], timeout: int = 300) -> str:
    r = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:300])
    return r.stdout


def parse_run_log(text: str) -> dict:
    """Counts from one run log (gh run view --log): the pre-BK (Sep 25) and the current formats."""
    passes, cur = [], None
    starved_by_pass: dict[int, list] = {}
    res = {"passes": 0, "passes_failed": 0, "failed_synth": 0, "failed_synth_429": 0, "total_429": 0,
           "breaker_open_passes": 0, "zero_baked_passes": 0, "baked": 0, "kind": "unknown",
           "last_breaker": None, "starved_last_pass": [], "loop_end": None}
    for line in text.splitlines():
        m = RE_PASS.search(line)
        if m:
            cur = int(m.group(1))
            passes.append(cur)
            continue
        if RE_PASS_FAILED.search(line):
            res["passes_failed"] += 1
        if RE_SYNTH_FAILED.search(line):
            res["failed_synth"] += 1
            if "429" in line:
                res["failed_synth_429"] += 1
        m = RE_STARVED.search(line)
        if m:
            starved_by_pass.setdefault(cur or 0, []).append((m.group(1), int(m.group(2))))
        m = RE_SUMMARY.search(line)
        if m:
            baked = int(m.group(1))
            res["baked"] += baked
            res["zero_baked_passes"] += 1 if baked == 0 else 0
            if m.group(4) is not None:
                res["total_429"] += int(m.group(4))
                res["last_breaker"] = m.group(6)
                res["breaker_open_passes"] += 1 if m.group(6) == "OPEN" else 0
            continue
        m = RE_RETEXT_SUMMARY.search(line)
        if m:
            res["kind"] = "retext_ids"
            res["total_429"] += int(m.group(3))
            res["last_breaker"] = m.group(5)
        m = RE_LOOP_END.search(line)
        if m and "echo" not in line:
            res["loop_end"] = [int(m.group(1)), int(m.group(2))]
    res["passes"] = len(passes)
    if passes:
        res["kind"] = "loop"
        # The last pass of a cancelled run has no summary: report the last pass that printed STARVED.
        for p in reversed(passes):
            if p in starved_by_pass:
                res["starved_last_pass"] = starved_by_pass[p]
                res["starved_pass"] = p
                break
    if res["total_429"] == 0 and res["failed_synth_429"]:
        res["total_429"] = res["failed_synth_429"]   # pre-BK logs print no 429 count
    return res


def run_findings(res: dict) -> list[str]:
    f = []
    if res["failed_synth"] > MAX_FAILED_SYNTH:
        f.append(f"{res['failed_synth']} failed synths in one run (> {MAX_FAILED_SYNTH}): the carry-forward is "
                 "hiding un-voiced stories")
    done = res["passes"]
    if done >= MIN_PASSES_FOR_SHARE and res["zero_baked_passes"] / max(1, done) > MAX_ZERO_PASS_SHARE:
        f.append(f"{res['zero_baked_passes']} of {done} passes baked nothing (> {MAX_ZERO_PASS_SHARE:.0%}): gTTS "
                 "throttled most of the run")
    return f


def gh_check() -> tuple[dict, list[str], bool]:
    """(report, findings, readable)."""
    rep, findings = {}, []
    try:
        private = gh(["api", f"repos/{REPO}", "-q", ".private"], timeout=60).strip()
        runs = json.loads(gh(["run", "list", "-R", REPO, "--workflow", WORKFLOW, "-L", "25", "--json",
                              "databaseId,status,conclusion,event,createdAt,updatedAt,headSha"], timeout=60))
    except Exception as e:
        return {"error": f"gh failed: {e}"}, [], False
    rep["private"] = private
    if private != "false":
        findings.append(f"repo {REPO} private={private}: Actions minutes run out on a private repo; make it public")
    now = time.time()

    def ts(s):
        return calendar.timegm(time.strptime(s, "%Y-%m-%dT%H:%M:%SZ"))

    rep["in_progress"] = [{"id": r["databaseId"], "status": r["status"], "event": r["event"], "sha": r["headSha"][:7],
                           "started": r["createdAt"], "elapsed_min": round((now - ts(r["createdAt"])) / 60),
                           "log": "not served by GitHub until the run completes"}
                          for r in runs if r["status"] != "completed"]
    rep["completed"] = []
    loop_seen = False
    for r in [r for r in runs if r["status"] == "completed"][:8]:
        try:
            text = gh(["run", "view", str(r["databaseId"]), "-R", REPO, "--log"], timeout=600)
        except Exception as e:
            rep["completed"].append({"id": r["databaseId"], "conclusion": r["conclusion"], "log_error": str(e)})
            continue
        res = parse_run_log(text)
        res.update(id=r["databaseId"], event=r["event"], conclusion=r["conclusion"], sha=r["headSha"][:7],
                   started=r["createdAt"], ended=r["updatedAt"],
                   minutes=round((ts(r["updatedAt"]) - ts(r["createdAt"])) / 60))
        res["findings"] = run_findings(res)
        rep["completed"].append(res)
        if res["kind"] == "loop":
            rep["latest_loop"] = res["id"]
            findings += [f"run {res['id']}: {x}" for x in res["findings"]]
            loop_seen = True
            break
    if not loop_seen:
        findings.append("no completed loop run among the latest 8 completed runs")
    return rep, findings, True


def print_gh(rep: dict) -> None:
    if not rep or "error" in rep:
        return
    print(f"\n# gh: repo private={rep.get('private')}")
    for r in rep.get("in_progress", []):
        print(f"{r['status']}: run {r['id']} ({r['event']}, {r['sha']}) created {r['started']}, {r['elapsed_min']} min ago; "
              f"{r['log']}")
    for r in rep.get("completed", []):
        if "log_error" in r:
            print(f"completed: run {r['id']} {r['conclusion']}: log unreadable ({r['log_error']})")
            continue
        print(f"completed: run {r['id']} {r['kind']} {r['conclusion']} ({r['event']}, {r['sha']}, {r['minutes']} min): "
              f"passes={r['passes']} failed_passes={r['passes_failed']} baked={r['baked']} "
              f"zero_baked_passes={r['zero_baked_passes']} 429s={r['total_429']} "
              f"breaker_open_passes={r['breaker_open_passes']} last_breaker={r['last_breaker']} "
              f"failed_synth={r['failed_synth']} starved={len(r['starved_last_pass'])}"
              + (f" (pass {r['starved_pass']})" if r.get("starved_pass") else ""))


# ---------- selftest ----------

def selftest(bake) -> list[str]:
    """Offline positive controls. Returns the list of failures (empty = the check works)."""
    fails = []
    drift = rule_drift(bake)
    if drift:
        fails.append(f"bake.plan_manifest no longer has {drift}: update bake_eligible() to its rule")
    m = {"manifest": "selftest", "phonetics": "kpop_en", "lang": "en"}
    now = int(time.time() * 1000)
    body = ("The agency confirmed the schedule on Friday and said the group will release a new album "
            "next month, with a world tour to follow in the spring.")
    feed = [{"id": "st_stub", "title": "", "summary": "", "source": "", "publishedAtMs": now - 60_000}]
    feed += [{"id": f"st_{i}", "title": f"Story number {i} makes the news", "summary": body,
              "source": "Selftest", "publishedAtMs": now - (i + 1) * 1800_000} for i in range(24)]
    feed.append(dict(feed[8]))   # duplicate id: bake keeps the first
    el = bake_eligible(bake, m, feed)
    ids = [a["id"] for a in el]
    if "st_stub" in ids:
        fails.append("a stub with no text is counted as eligible")
    if len(ids) != len(set(ids)) or len(ids) != 24:
        fails.append(f"eligible ids wrong: {ids}")
    if ids[:3] != ["st_0", "st_1", "st_2"]:
        fails.append(f"eligible items are not newest first: {ids[:3]}")
    allids = set(ids)
    pub = {a["id"]: bake._pub_ms(a) for a in el}
    good = evaluate(bake, "selftest", el, allids, lambda aid: True, now, K_DEFAULT)
    if good["findings"] or good["warns"] or good["newest"]["coverage"] != 1.0:
        fails.append(f"a complete manifest is flagged: {good['findings'] + good['warns']}")
    # The control the round asked for: a manifest missing its newest stories (the newest 8: 0.5-4 h old).
    missing_newest = evaluate(bake, "selftest", el, allids - set(ids[:8]), lambda aid: True, now, K_DEFAULT)
    if not missing_newest["findings"]:
        fails.append("a manifest missing its 8 newest stories is NOT flagged")
    # Listed, but the MP3 404s (a manifest must never list an un-baked id).
    no_mp3 = evaluate(bake, "selftest", el, allids, lambda aid: aid not in set(ids[:8]), now, K_DEFAULT)
    if not no_mp3["findings"]:
        fails.append("a manifest whose 8 newest MP3s 404 is NOT flagged")
    nothing = evaluate(bake, "selftest", el, set(), lambda aid: False, now, K_DEFAULT)
    if not any("none of" in f for f in nothing["findings"]):
        fails.append("a manifest with nothing voiced is NOT flagged")
    transient = evaluate(bake, "selftest", el, allids, lambda aid: None if aid in set(ids[:8]) else True, now, K_DEFAULT)
    if transient["findings"]:
        fails.append("a transient HEAD (unknown) is counted as a miss")
    young_missing = evaluate(bake, "selftest", el, allids - set(ids[:2]), lambda aid: True, now, K_DEFAULT)
    if young_missing["findings"] or young_missing["warns"]:
        fails.append("the 2 newest stories (under an hour old) not yet voiced is flagged")
    # Newest first under the gTTS budget: settled middle skipped, newest voiced = WARN only.
    settled6 = [i for i in ids if now - pub[i] >= GRACE_H * 3.6e6][:6]
    backlog = evaluate(bake, "selftest", el, allids - set(settled6), lambda aid: True, now, K_DEFAULT)
    if backlog["findings"] or not backlog["warns"]:
        fails.append(f"a skipped settled backlog is not a WARN-only row: {backlog['findings']} {backlog['warns']}")
    # Fleet floors: Sep 25 (every manifest stalled) is flagged, a healthy fleet is not.
    if not fleet_findings(fleet([missing_newest] * 3)):
        fails.append("a fleet of manifests missing their newest stories is NOT flagged")
    if fleet_findings(fleet([good, backlog, good, young_missing])):
        fails.append("a healthy fleet is flagged")
    # --gh parser: the Sep 25 run that hid 6,183 failed synths must be flagged; the Sep 26 run must not.
    for fname, must_flag in (("run_36174562701_excerpt.log.gz", True), ("run_36230985595_excerpt.log.gz", False)):
        p = os.path.join(GH_CONTROLS, fname)
        if not os.path.exists(p):
            fails.append(f"gh control missing: {p}")
            continue
        with gzip.open(p, "rt", encoding="utf-8") as f:
            res = parse_run_log(f.read())
        flagged = bool(run_findings(res))
        if flagged != must_flag:
            fails.append(f"gh control {fname}: flagged={flagged}, expected {must_flag} ({res})")
    return fails


# ---------- CLI ----------

def pct(c):
    return "n/a" if c["coverage"] is None else f"{c['ok']}/{c['known']} {c['coverage']:.0%}"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--k", type=int, default=K_DEFAULT, help="newest eligible feed stories per manifest")
    ap.add_argument("--manifests", help="comma list (default: every bake.MANIFESTS entry)")
    ap.add_argument("--gh", action="store_true", help="also read the latest workflow runs and the repo visibility")
    ap.add_argument("--json", help="write the full result here")
    ap.add_argument("--selftest", action="store_true", help="run the positive controls only")
    a = ap.parse_args()
    t0 = time.monotonic()
    bake = load_bake()
    fails = selftest(bake)
    if fails:
        for f in fails:
            print("SELFTEST FAILED:", f)
        return 2
    print("selftest: PASS (eligibility stub/dup/order; complete, young-missing and backlog manifests not "
          "flagged; missing-newest, 404-MP3 and nothing-voiced flagged; transient not a miss; fleet floors; "
          "gh Sep 25 run flagged, Sep 26 run clean)")
    if a.selftest:
        return 0
    want = set(a.manifests.split(",")) if a.manifests else None
    mans = [m for m in bake.MANIFESTS if not want or m["manifest"] in want]
    if want and len(mans) != len(want):
        print("unknown manifest(s):", sorted(want - {m["manifest"] for m in mans}))
        return 2
    rows, unread, live_inputs = [], [], {}
    now = int(time.time() * 1000)
    for m in mans:
        name = m["manifest"]
        try:
            feed = get_json(m["feed_url"]).get("items", [])
            man = get_json(f"{MANIFEST_BASE}/{name}.json")
        except Exception as e:
            unread.append([name, f"{type(e).__name__}: {e}"])
            print(f"[{name}] UNREAD: {e}")
            continue
        el = bake_eligible(bake, m, feed)
        mids = {x.get("id") for x in man.get("items", []) if isinstance(x, dict)}
        cache: dict = {}

        def served(aid, _c=cache):
            if aid not in _c:
                _c[aid] = head_status(f"{MANIFEST_BASE}/{bake.article_key(aid)}")
            return _c[aid]

        row = evaluate(bake, name, el, mids, served, now, a.k)
        live_inputs[name] = (el, mids, served)
        row.update(feed_items=len(feed), eligible=len(el), manifest_items=len(mids),
                   generated_age_h=round((now - int(man.get("generatedAtMs") or 0)) / 3.6e6, 2))
        rows.append(row)
        print(f"[{name:13}] newest {pct(row['newest'])}; settled {pct(row['settled'])}; newest feed "
              f"{row['newest_feed_age_h']} h, newest voiced {row['newest_voiced_age_h']} h, lag {row['lag_h']} h; "
              f"manifest written {row['generated_age_h']} h ago"
              + ("".join(f" <-- FINDING {x}" for x in row["findings"])) + ("".join(f" <-- WARN {x}" for x in row["warns"])),
              flush=True)
    findings = [f"[{r['manifest']}] {x}" for r in rows for x in r["findings"]]
    warns = [f"[{r['manifest']}] {x}" for r in rows for x in r["warns"]]
    fl = fleet(rows)
    findings += fleet_findings(fl)
    # Live positive control: the first manifest without a finding, minus its 8 newest ids, must be flagged.
    live_control = None
    for r in rows:
        el, mids, served = live_inputs[r["manifest"]]
        if not r["findings"] and len(el) >= 10:
            probe = evaluate(bake, r["manifest"], el, mids - {x["id"] for x in el[:8]}, served, now, a.k)
            if probe["lag_h"] is None or bake._pub_ms(el[0]) - bake._pub_ms(el[8]) <= MAX_LAG_H * 3.6e6:
                continue   # a feed whose 9 newest stories span < MAX_LAG_H cannot show a lag; try the next
            live_control = {"manifest": r["manifest"], "flagged": bool(probe["findings"])}
            print(f"live control: {r['manifest']} with its 8 newest ids removed -> "
                  f"{'flagged' if probe['findings'] else 'NOT FLAGGED'}")
            if not probe["findings"]:
                print("CONTROL FAILED: a live manifest missing its newest stories is not flagged")
                return 2
            break
    gh_rep = None
    if a.gh:
        try:
            gh_rep, gh_findings, readable = gh_check()
        except Exception as e:
            gh_rep, gh_findings, readable = {"error": f"{type(e).__name__}: {e}"}, [], False
        if not readable:
            print("--gh: UNREAD:", gh_rep.get("error"))
        findings += [f"[gh] {x}" for x in gh_findings]
        print_gh(gh_rep)
    elapsed = time.monotonic() - t0
    print(f"\nfleet over {len(rows)} manifests ({len(unread)} unread): newest {pct(fl['newest'])} "
          f"(floor {FLOOR_FLEET_NEWEST:.0%}), settled {pct(fl['settled'])} (floor {FLOOR_FLEET_SETTLED:.0%}); "
          f"max lag {max((r['lag_h'] or 0) for r in rows) if rows else 'n/a'} h (ceiling {MAX_LAG_H} h); {elapsed:.0f} s")
    for w in warns:
        print("WARN", w)
    for f in findings:
        print("FINDING", f)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump({"checked_at_ms": now, "k": a.k, "fleet": fl,
                       "floors": {"grace_h": GRACE_H, "max_lag_h": MAX_LAG_H, "fleet_newest": FLOOR_FLEET_NEWEST,
                                  "fleet_settled": FLOOR_FLEET_SETTLED, "warn_settled": WARN_SETTLED,
                                  "max_failed_synth": MAX_FAILED_SYNTH, "max_zero_pass_share": MAX_ZERO_PASS_SHARE},
                       "rows": rows, "unread": unread, "live_control": live_control, "gh": gh_rep,
                       "warns": warns, "findings": findings, "elapsed_s": round(elapsed)},
                      fh, ensure_ascii=False, indent=1)
        print("wrote", a.json)
    if not rows:
        print("NOTHING READ: a check that read nothing is not a pass")
        return 2
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
