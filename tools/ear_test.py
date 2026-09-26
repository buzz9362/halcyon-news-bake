"""Ear test of the SERVED baked MP3s (Sep 26 2026: lane RV wrote it, lane WK made it a weekly tool).

A pronunciation or text fix on the baked path is DONE only when the MP3 the car plays says it. This
tool downloads <R2 base>/<sha256(id)[:32]>.mp3, checks its Last-Modified against the fix time,
transcribes it with faster_whisper (one model loaded at a time, one file at a time, word
timestamps, below-normal priority) and compares what was heard with what bake.py voices today
(bake.sanitize_article + text_for + apply_phonetics):
  (a) expected words are heard as often as the voiced text says them (Tiffany, Karina, Johnny and
      Jackson Wang are expected whenever the story's text has them);
  (b) forbidden fragments (handles, old respellings: "chaechae", "Tih fa nee", "TfA Nae", ...) are
      not heard more often than the voiced text itself says them;
  (c) extra checks: a social handle in the voiced text (bake.SOCIAL_HANDLE_RE), "hashtag" heard,
      an ALL-CAPS word the SPEECH_NORMALIZE pass should have Title-cased (bake.LETTER_ACRONYMS and
      bake._has_vowel are the SSOT) heard spelled out letter by letter, and code heard (function,
      window, document, querySelector, addEventListener) that the voiced text does not contain;
  (d) the headline cut: the end of the last headline word and the start of the first summary word;
      gap_ms < 250 is a WARN (no audible pause for the app's headline cut; tiny's timestamps are
      coarse, so it never fails a story). With cut_ms, cut + 400 ms must land before the summary.

Modes:
  python tools/ear_test.py --sample 2                      # 2 newest voiced stories per manifest
  python tools/ear_test.py --sample 3 --manifests kpop_en,circuitly_de
  python tools/ear_test.py --fixed-after 2026-09-26T04:42:33Z --case kpop_en:rss_1oweqv3 [--case ...]
  python tools/ear_test.py --fixed-after <ISO|epoch ms> --cases cases.json
  python tools/ear_test.py --selftest                      # the positive controls only
      cases.json: [{"manifest": "kpop_en", "id": "rss_1oweqv3", "expect": ["Tiffany"],
                    "forbid": ["Tih fa nee"], "cut_ms": 5200, "label": "...",
                    "mp3": "<optional local file: pre-flight a fix before it is served>"}]
  --case also takes extra fields: kpop_en:rss_x:expect=Word|Two words:forbid=frag|frag:cut_ms=5200
  --sample N takes, per manifest in bake.MANIFESTS (or --manifests), the N newest items whose MP3
      answers HEAD 200; a 404 is reported as NOT VOICED (a listed story the car cannot play) and is
      not tested. --fixed-after is optional there (default 0: no staleness check).
  --out <prefix>      writes <prefix>.json and <prefix>.txt (default: the non-public store,
                      App Market Submission/_source_health/state/ear/ear_<mode>_<utc>)
  --model NAME        default small.en for en, tiny for every other language (the only cached
                      multilingual model; a download needs --allow-download and the owner's OK)

Selftest (always run first by --sample; alone with --selftest): the controls in
_source_health/controls/ear/ are real served MP3s saved with the voiced text of their story. The
OLD Sep 25 Tiffany audio (whisper hears "TfA-Nae") and the OLD Sep 26 PC-Welt audio (40 s of
JavaScript; tiny hears "Queryselector") must FAIL with their fragment heard; the re-voiced MP3s of
the same two stories must PASS. Anything else means the tool cannot hear a defect: exit 2.

Exit 0 = every tested story PASSES (WARNs allowed), 1 = a FAIL, 2 = the selftest broke, nothing was
tested, or a story could not be checked (ERROR: network/model; rerun later, never read as a pass).
Measured Sep 26 2026 10:18Z: --sample 2 over all 27 manifests (54 stories + the 4 controls) took
116 s wall on this PC (8 GB GPU, small.en then tiny, one model at a time): 54/54 PASS, 1 gap WARN.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import difflib
import email.utils
import gc
import hashlib
import importlib.util
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the baker repo
BASE = "https://pub-fcb63a0a41b446ea825306ef86fc224f.r2.dev"   # BAKED_MANIFEST_BASE in the apps
UA = {"User-Agent": "halcyon-news-bake ear_test (Soundica QA; one file at a time)"}
# The MP3 cache lives outside the repo and outside OneDrive.
CACHE = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "halcyon-ear-cache")
# The non-public store (no git remote): control MP3s and the default reports.
STORE = os.environ.get("HALCYON_SOURCE_HEALTH") or os.path.join(
    os.path.dirname(ROOT), "App Market Submission", "_source_health")
CONTROLS = os.path.join(STORE, "controls", "ear")

DEFAULT_NAMES = ["Tiffany", "Karina", "Johnny", "Jackson Wang"]
# How whisper spells a CORRECT English reading of a name ("Wang" read /wahng/ is written "Wong").
ALIASES = {"Jackson Wang": ["Jackson Wong"]}
# Names the ASR cannot tell apart from their old respelling: whisper small.en also writes the
# Sep 24 "Jak sun Wahng" audio as "Jackson Wong". For these the proof is the served MP3 being
# newer than the fix plus the voiced text; the ear check alone is marked not discriminating.
NOT_DISCRIMINATING = {"Jackson Wang": "whisper small.en hears the old 'Jak sun Wahng' as 'Jackson Wong' too"}
# Handles, and the old respellings (Sep 25 tables) plus what whisper wrote for them on the old
# audio ("TfA-Nae" for the Sep 25 Tiffany, the owner's "t f n a"). A fragment counts only when it
# is heard MORE often than the voiced text says it ("Kareena" is a real Bollywood name).
DEFAULT_FORBID = ["chaechae", "chae chae", "underscore", "Tih fa nee", "TfA Nae", "t f n a", "Jo Nae",
                  "Ka ree na", "Jah nee", "Jak sun", "Yak Son"]
# Code heard that the voiced text does not contain (Sep 26 PC-Welt sticky promo JS). One of the
# STRONG ones is a FAIL; the WEAK ones are ordinary words, so it takes two extra hearings to FAIL.
CODE_STRONG = ["querySelector", "addEventListener", "getElementById"]
CODE_WEAK = ["function", "window", "document"]
CUT_MARGIN_MS = 400
GAP_WARN_MS = 250
LONG_WORD_MS = 800   # a first summary word this long usually carries the pause inside it
SCAN_EXTRA = 10          # --sample: HEAD at most N + this many items per manifest
BELOW_NORMAL_PRIORITY_CLASS = 0x4000


# ---------- helpers ----------

def lower_priority() -> None:
    """The owner must be able to use the PC while this runs."""
    try:
        if os.name == "nt":
            import ctypes
            k32 = ctypes.windll.kernel32
            k32.SetPriorityClass(k32.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS)
        else:
            os.nice(10)
    except Exception:
        pass


def add_cuda_dll_dirs() -> None:
    """ctranslate2 needs cublas64_12.dll / cudnn at the first encode. On this PC they come from the
    nvidia-* wheels (site-packages/nvidia/<lib>/bin), which are not on PATH; without this the first
    encode raises "cublas64_12.dll is not found" and a second attempt hung."""
    import site
    for sp in site.getsitepackages():
        for sub in ("cublas", "cudnn", "cuda_nvrtc"):
            d = os.path.join(sp, "nvidia", sub, "bin")
            if os.path.isdir(d):
                os.add_dll_directory(d)
                os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


def parse_time_ms(s: str) -> int:
    if re.fullmatch(r"\d{1,14}", s):
        return int(s)
    t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return int(t.timestamp() * 1000)


def iso(ms: int | None) -> str | None:
    if ms is None:
        return None
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def key_of(aid: str) -> str:
    return hashlib.sha256(aid.encode("utf-8")).hexdigest()[:32] + ".mp3"


def http(url: str, method: str = "GET"):
    req = urllib.request.Request(url, method=method, headers=UA)
    return urllib.request.urlopen(req, timeout=60)


def head_mp3(aid: str, tries: int = 2):
    """(True, last_modified_ms) on 200, (False, None) on 404/403, (None, None) when transient."""
    for n in range(tries):
        try:
            with http(f"{BASE}/{key_of(aid)}", "HEAD") as r:
                lm = r.headers.get("Last-Modified")
                return True, (int(email.utils.parsedate_to_datetime(lm).timestamp() * 1000) if lm else None)
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return False, None
        except Exception:
            pass
        time.sleep(1.5)
    return None, None


def norm_tokens(s: str) -> list[str]:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.split()


def count_seq(tokens: list[str], phrase: list[str]) -> int:
    n = len(phrase)
    return sum(1 for i in range(len(tokens) - n + 1) if tokens[i:i + n] == phrase) if n else 0


def count_sub(hay: str, needle: str) -> int:
    return hay.count(needle) if needle else 0


def load_bake():
    for k, v in (("R2_ACCESS_KEY_ID", "x"), ("R2_SECRET_ACCESS_KEY", "x"),
                 ("R2_ENDPOINT_URL", "https://example.invalid")):
        os.environ.setdefault(k, v)
    spec = importlib.util.spec_from_file_location("bake_ear", os.path.join(ROOT, "bake.py"))
    m = importlib.util.module_from_spec(spec)
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            spec.loader.exec_module(m)
    finally:
        os.chdir(cwd)
    return m


def voiced_text(bake, article: dict, phon: str) -> tuple[str, str]:
    """(full spoken text, spoken headline part) as bake.py voices them today."""
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            a = bake.sanitize_article(article)
            full = bake.apply_phonetics(bake.text_for(a), phon)
            head = bake.apply_phonetics(bake.text_for(dict(a, summary="")), phon)
    finally:
        os.chdir(cwd)
    return full, head


def default_model(lang: str) -> str:
    return "small.en" if lang == "en" else "tiny"


class OneModel:
    """At most ONE whisper model in memory (and on the GPU) at a time."""

    def __init__(self, args):
        self.args, self.name, self.model = args, None, None

    def get(self, name: str):
        if name != self.name:
            self.close()
            from faster_whisper import WhisperModel
            dev = self.args.device
            self.model = WhisperModel(name, device=dev, compute_type="float16" if dev == "cuda" else "int8",
                                      cpu_threads=2, num_workers=1, local_files_only=not self.args.allow_download)
            self.name = name
        return self.model

    def close(self):
        if self.model is not None:
            del self.model
            self.model, self.name = None, None
            gc.collect()


# ---------- one story ----------

def fetch_served(aid: str) -> tuple[str, int | None, str]:
    url = f"{BASE}/{key_of(aid)}"
    with http(url, "HEAD") as r:
        lm = r.headers.get("Last-Modified")
    mod = int(email.utils.parsedate_to_datetime(lm).timestamp() * 1000) if lm else None
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"{key_of(aid)[:-4]}_{mod}.mp3")
    if not os.path.exists(path):
        with http(url) as r:
            data = r.read()
        with open(path + ".part", "wb") as f:
            f.write(data)
        os.replace(path + ".part", path)
    return url, mod, path


def align_cut(exp_tokens: list[str], head_len: int, words: list[dict]) -> dict:
    heard = [w["norm"] for w in words]
    sm = difflib.SequenceMatcher(None, exp_tokens, heard, autojunk=False)
    first_sum = last_head = None
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            ei, hi = a + k, b + k
            if ei < head_len:
                last_head = (ei, hi)
            elif first_sum is None:
                first_sum = (ei, hi)
    res = {"headline_words": head_len,
           "summary_first_word": exp_tokens[head_len] if head_len < len(exp_tokens) else None}
    if last_head:
        w = words[last_head[1]]
        res.update(last_headline_word=w["word"], headline_end_ms=int(w["end"] * 1000),
                   headline_last_word_exact=last_head[0] == head_len - 1)
    if first_sum:
        w = words[first_sum[1]]
        res.update(first_summary_word_heard=w["word"], summary_start_ms=int(w["start"] * 1000),
                   summary_word_offset=first_sum[0] - head_len,
                   summary_word_ms=int((w["end"] - w["start"]) * 1000))
    if last_head and first_sum:
        res["gap_ms"] = res["summary_start_ms"] - res["headline_end_ms"]
    return res


def caps_left(bake, text: str) -> list[str]:
    """ALL-CAPS words of 4+ letters the SPEECH_NORMALIZE pass Title-cases (not an acronym of
    bake.LETTER_ACRONYMS, has a vowel by bake._has_vowel, not "(BRACKETED)") that are still caps."""
    out = []
    for i, j, tok in bake._caps_tokens(text):
        w = tok.split("'")[0]
        if not (len(w) >= 4 and w.isalpha() and w.upper() == w and w.lower() != w):
            continue
        if i > 0 and text[i - 1] == "(" and j < len(text) and text[j] == ")":
            continue
        if w.upper() in bake.LETTER_ACRONYMS or not bake._has_vowel(w):
            continue
        out.append(w)
    return sorted(set(out))


def letter_runs(tokens: list[str]) -> list[str]:
    runs, run = [], ""
    for t in tokens + [""]:
        if len(t) == 1 and t.isalpha():
            run += t
        else:
            if len(run) >= 3:
                runs.append(run)
            run = ""
    return runs


def extra_checks(bake, full: str, heard_tokens: list[str], text_tokens: list[str]) -> tuple[dict, list, list]:
    """(details, problems, warns) beyond (a)/(b)."""
    problems, warns = [], []
    d = {}
    handles = [m.group(0) for m in bake.SOCIAL_HANDLE_RE.finditer(full)]
    if "view this post on instagram" in full.lower():
        handles.append("<embed placeholder>")
    d["handle_in_text"] = handles
    if handles:
        problems.append(f"voiced text carries a social handle {handles}")
    ht_text = count_seq(text_tokens, ["hashtag"]) + count_seq(text_tokens, ["hash", "tag"])
    ht_heard = count_seq(heard_tokens, ["hashtag"]) + count_seq(heard_tokens, ["hash", "tag"])
    d.update(hashtag_in_text=ht_text, hash_sign_in_text=full.count("#"), hashtag_heard=ht_heard)
    if ht_heard > ht_text:
        problems.append(f"'hashtag' heard x{ht_heard}" + (" (a single '#' in the voiced text: bake strips only runs of 2+)"
                                                          if full.count("#") else ""))
    caps = caps_left(bake, full)
    runs = letter_runs(heard_tokens)
    spelled = [c for c in caps if any(c.lower() in r or (r in c.lower() and len(r) >= len(c) - 1) for r in runs)]
    d.update(caps_left=caps, caps_spelled_out=spelled)
    if spelled:
        problems.append(f"ALL-CAPS word heard spelled out letter by letter: {spelled}")
    elif caps:
        warns.append(f"ALL-CAPS word left in the voiced text (the caps pass did not Title-case it): {caps}")
    sq_heard, sq_text = "".join(heard_tokens), "".join(text_tokens)
    code = {}
    for w in CODE_STRONG:
        n = "".join(norm_tokens(w))
        code[w] = count_sub(sq_heard, n) - count_sub(sq_text, n)
    for w in CODE_WEAK:
        code[w] = count_seq(heard_tokens, [w]) - count_seq(text_tokens, [w])
    code = {k: v for k, v in code.items() if v > 0}
    d["code_heard"] = code
    weak = sum(v for k, v in code.items() if k in CODE_WEAK)
    if any(k in CODE_STRONG for k in code) or weak >= 2:
        problems.append(f"code heard that the voiced text does not say: {code}")
    elif weak == 1:
        warns.append(f"one code-like word heard beyond the voiced text: {code}")
    return d, problems, warns


def analyze(bake, models: OneModel, args, *, manifest: str, aid: str, lang: str, full: str, head: str,
            path: str, url: str, mod: int | None, fixed_after: int, stale: bool, case: dict) -> dict:
    model_name = args.model or default_model(lang)
    t0 = time.monotonic()
    segs, info = models.get(model_name).transcribe(
        path, language=None if model_name.endswith(".en") else lang, beam_size=5, temperature=0.0,
        word_timestamps=True, condition_on_previous_text=False, vad_filter=False)
    words, spoken = [], []
    for s in segs:
        for w in s.words or []:
            spoken.append(w.word.strip())
            for tok in norm_tokens(w.word):
                words.append({"word": w.word.strip(), "norm": tok, "start": round(w.start, 3),
                              "end": round(w.end, 3), "p": round(w.probability, 3)})
    asr_s = time.monotonic() - t0
    heard_tokens = [w["norm"] for w in words]
    transcript = " ".join(spoken)
    exp_tokens = norm_tokens(full)
    best_effort = not model_name.endswith(".en") and lang != "en"   # tiny on a non-English story

    problems, warns = [], []
    if stale:
        problems.append(f"served MP3 Last-Modified {iso(mod)} is before the fix {iso(fixed_after)}: re-voice pending")
    expects = []
    wanted = [(p, True) for p in case.get("expect", [])]
    for nm in DEFAULT_NAMES:
        if count_seq(exp_tokens, norm_tokens(nm)) and nm not in [w for w, _ in wanted]:
            wanted.append((nm, False))
    for phrase, explicit in wanted:
        ph = norm_tokens(phrase)
        need = max(1, count_seq(exp_tokens, ph))
        got = count_seq(heard_tokens, ph) + sum(count_seq(heard_tokens, norm_tokens(al)) for al in ALIASES.get(phrase, []))
        ok = got >= need
        expects.append({"phrase": phrase, "in_text": count_seq(exp_tokens, ph), "heard": got, "ok": ok,
                        "accepts": [phrase] + ALIASES.get(phrase, []),
                        "discriminating": phrase not in NOT_DISCRIMINATING,
                        "note": NOT_DISCRIMINATING.get(phrase, "")})
        if not ok:
            msg = f"expected '{phrase}' x{need}, heard x{got}"
            if best_effort and not explicit:
                warns.append(msg + f" ({model_name} on {lang}: best-effort name hearing)")
            else:
                problems.append(msg)
    forbids = []
    sq_heard, sq_text = "".join(heard_tokens), "".join(exp_tokens)
    for frag in list(dict.fromkeys(DEFAULT_FORBID + list(case.get("forbid", [])))):
        f = "".join(norm_tokens(frag))
        n_heard, n_text = count_sub(sq_heard, f), count_sub(sq_text, f)
        hit = n_heard > n_text
        forbids.append({"fragment": frag, "heard": hit, "heard_count": n_heard, "text_count": n_text})
        if hit:
            problems.append(f"forbidden '{frag}' heard")
    extra, p2, w2 = extra_checks(bake, full, heard_tokens, exp_tokens)
    problems += p2
    warns += w2
    cut = align_cut(exp_tokens, len(norm_tokens(head)), words)
    if cut.get("gap_ms") is not None and cut["gap_ms"] < GAP_WARN_MS:
        long_word = cut.get("summary_word_ms", 0) >= LONG_WORD_MS
        warns.append(f"gap {cut['gap_ms']} ms < {GAP_WARN_MS} ms: no audible pause for the headline cut"
                     + (f" (the first summary word lasts {cut['summary_word_ms']} ms: whisper may have attached "
                        "the pause to it; listen before acting)" if long_word else ""))
    if case.get("cut_ms") is not None:
        cm = int(case["cut_ms"])
        cut["cut_ms"] = cm
        if "summary_start_ms" not in cut:
            problems.append("cut check: first summary word not found in the audio")
        elif cm + CUT_MARGIN_MS > cut["summary_start_ms"]:
            problems.append(f"cut {cm} ms + {CUT_MARGIN_MS} ms is past the first summary word at {cut['summary_start_ms']} ms")
    return {
        "label": case.get("label", ""), "manifest": manifest, "id": aid, "url": url, "lang": lang,
        "last_modified": iso(mod), "last_modified_ms": mod, "fixed_after": iso(fixed_after), "stale": stale,
        "model": model_name, "asr_seconds": round(asr_s, 1), "duration_s": round(info.duration, 2),
        "expect": expects, "forbid": forbids, "extra": extra, "cut": cut,
        "content_ok": not [p for p in problems if "re-voice pending" not in p],
        "verdict": "PASS" if not problems else "FAIL", "problems": problems, "warns": warns,
        "voiced_text": full, "transcript": transcript, "words": words,
    }


class Manifests:
    def __init__(self):
        self._c = {}

    def items(self, name: str) -> list:
        if name not in self._c:
            with http(f"{BASE}/{name}.json") as r:
                self._c[name] = json.loads(r.read().decode("utf-8")).get("items", [])
        return self._c[name]


def run_case(case: dict, fixed_after: int, bake, models: OneModel, args, mans: Manifests) -> dict:
    name, aid = case["manifest"], case["id"]
    mcfg = next((m for m in bake.MANIFESTS if m["manifest"] == name), None)
    if mcfg is None:
        return {"manifest": name, "id": aid, "verdict": "ERROR", "problems": [f"unknown manifest {name}"]}
    article = case.get("article") or next((a for a in mans.items(name) if isinstance(a, dict) and a.get("id") == aid), None)
    if article is None:
        return {"manifest": name, "id": aid, "verdict": "ERROR", "problems": ["id not in the served manifest"]}
    full, head = voiced_text(bake, article, mcfg["phonetics"])
    if case.get("mp3"):   # a local file (pre-flight of a fix before it is served); no staleness
        url, path = f"file:{case['mp3']}", case["mp3"]
        mod, stale = int(os.path.getmtime(path) * 1000), False
    else:
        url, mod, path = fetch_served(aid)
        stale = mod is None or mod < fixed_after
    return analyze(bake, models, args, manifest=name, aid=aid, lang=mcfg["lang"], full=full, head=head,
                   path=path, url=url, mod=mod, fixed_after=fixed_after, stale=stale, case=case)


# ---------- selftest (positive controls) ----------

def load_controls() -> list[dict]:
    out = []
    if not os.path.isdir(CONTROLS):
        return out
    for fn in sorted(os.listdir(CONTROLS)):
        if fn.endswith(".json"):
            with open(os.path.join(CONTROLS, fn), encoding="utf-8") as f:
                c = json.load(f)
            c["_mp3"] = os.path.join(CONTROLS, c["mp3"])
            out.append(c)
    return out


def selftest(bake, models: OneModel, args) -> tuple[bool, list[dict], list[str]]:
    """(ok, results, messages). A bad control must FAIL with its fragment heard, a clean one PASS."""
    ctrls = load_controls()
    msgs, results = [], []
    bad = [c for c in ctrls if c.get("expect_verdict") == "FAIL"]
    good = [c for c in ctrls if c.get("expect_verdict") == "PASS"]
    if not bad or not good:
        return False, [], [f"controls missing in {CONTROLS} (need at least one FAIL and one PASS control)"]
    for c in sorted(ctrls, key=lambda c: c.get("model") or default_model(c["lang"])):
        if not os.path.exists(c["_mp3"]):
            msgs.append(f"control MP3 missing: {c['_mp3']}")
            continue
        a = argparse.Namespace(**vars(args))
        a.model = c.get("model") or args.model
        try:
            r = analyze(bake, models, a, manifest=c["manifest"], aid=c["id"], lang=c["lang"],
                        full=c["voiced_text"], head=c["headline_text"], path=c["_mp3"], url=f"file:{c['mp3']}",
                        mod=c.get("served_last_modified_ms"), fixed_after=0, stale=False,
                        case={"expect": c.get("expect", []), "forbid": c.get("forbid", []), "label": c["name"]})
        except Exception as e:
            msgs.append(f"control {c['name']}: {type(e).__name__}: {e}")
            continue
        r["control"] = c["name"]
        results.append(r)
        heard_sq = "".join(w["norm"] for w in r["words"])
        if c["expect_verdict"] == "FAIL":
            missing = [f for f in c.get("must_hear", []) if "".join(norm_tokens(f)) not in heard_sq]
            if r["verdict"] != "FAIL":
                msgs.append(f"BAD control {c['name']} PASSED: the tool cannot hear '{c.get('must_hear')}'")
            elif missing:
                msgs.append(f"BAD control {c['name']} failed, but {missing} was not heard (model drift?)")
        elif r["verdict"] != "PASS":
            msgs.append(f"CLEAN control {c['name']} FAILED: {r['problems']}")
    return not msgs and len(results) == len(ctrls), results, msgs


# ---------- sample ----------

def sample_cases(bake, n: int, names: list[str], mans: Manifests) -> tuple[list[dict], list[dict], list[dict]]:
    """(cases, not_voiced, unread)."""
    cases, not_voiced, unread = [], [], []
    for m in bake.MANIFESTS:
        name = m["manifest"]
        if names and name not in names:
            continue
        try:
            items = [a for a in mans.items(name) if isinstance(a, dict) and a.get("id")]
        except Exception as e:
            unread.append({"manifest": name, "problem": f"manifest unreadable: {type(e).__name__}: {e}"})
            continue
        seen, ordered = set(), []
        for a in sorted(items, key=bake._pub_ms, reverse=True):
            if a["id"] not in seen:
                seen.add(a["id"])
                ordered.append(a)
        got = scanned = 0
        for a in ordered:
            if got >= n or scanned >= n + SCAN_EXTRA:
                break
            scanned += 1
            ok, _ = head_mp3(a["id"])
            if ok is False:
                not_voiced.append({"manifest": name, "id": a["id"], "published": iso(bake._pub_ms(a)),
                                   "title": (a.get("title") or "")[:90]})
                continue
            if ok is None:
                unread.append({"manifest": name, "id": a["id"], "problem": "HEAD transient (timeout/5xx)"})
                continue
            cases.append({"manifest": name, "id": a["id"], "article": a, "label": f"sample {got + 1}/{n}"})
            got += 1
        if got < n:
            unread.append({"manifest": name, "problem": f"only {got}/{n} voiced stories found in {scanned} scanned"})
    return cases, not_voiced, unread


# ---------- report ----------

def parse_case(s: str) -> dict:
    parts = s.split(":")
    if len(parts) < 2:
        raise SystemExit(f"--case needs manifest:id, got {s!r}")
    c = {"manifest": parts[0], "id": parts[1]}
    for extra in parts[2:]:
        k, _, v = extra.partition("=")
        if k in ("expect", "forbid"):
            c[k] = [x for x in v.split("|") if x]
        elif k == "cut_ms":
            c[k] = int(v)
        elif k == "label":
            c[k] = v
    return c


def story_lines(r: dict) -> list[str]:
    out = [f"{r['verdict']}  {r['manifest']}:{r['id']}  {r.get('label', '')}"]
    if r["verdict"] == "ERROR":
        return out + [f"  - {p}" for p in r["problems"]] + [""]
    out.append(f"  served {r['last_modified']} ({'STALE, re-voice pending' if r['stale'] else 'ok vs fix time'}); "
               f"{r['duration_s']} s audio; model {r['model']}; content {'OK' if r['content_ok'] else 'WRONG'}")
    for e in r["expect"]:
        out.append(f"  expect {e['phrase']!r}: in text x{e['in_text']}, heard x{e['heard']} {'ok' if e['ok'] else 'MISSING'}"
                   + ("" if e.get("discriminating", True) else f" (NOT discriminating: {e['note']}; rely on Last-Modified + voiced text)"))
    hits = [f["fragment"] for f in r["forbid"] if f["heard"]]
    x = r.get("extra", {})
    out.append(f"  forbidden fragments heard: {hits or 'none'}; code heard: {x.get('code_heard') or 'none'}; "
               f"hashtag heard x{x.get('hashtag_heard', 0)}; caps left {x.get('caps_left') or 'none'}; "
               f"handles in text {x.get('handle_in_text') or 'none'}")
    c = r["cut"]
    out.append(f"  headline ends {c.get('headline_end_ms')} ms ({c.get('last_headline_word')!r}); first summary word "
               f"{c.get('summary_first_word')!r} starts {c.get('summary_start_ms')} ms (heard {c.get('first_summary_word_heard')!r}, "
               f"offset {c.get('summary_word_offset')}); gap_ms {c.get('gap_ms')}"
               + (f"; cut {c['cut_ms']} ms" if "cut_ms" in c else ""))
    out.append(f"  heard: {r['transcript'][:400]}")
    out += [f"  - {p}" for p in r["problems"]]
    out += [f"  WARN {w}" for w in r.get("warns", [])]
    out.append("")
    return out


def text_report(mode: str, results: list[dict], fixed_after: int, st: dict, not_voiced: list, unread: list,
                wall_s: float) -> str:
    out = [f"Ear test ({mode}) {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}; fix time {iso(fixed_after)}; "
           f"wall {wall_s:.0f} s", ""]
    if st:
        out.append(f"SELFTEST {'PASS' if st['ok'] else 'BROKEN'}: " + ("; ".join(st["messages"]) or
                   ", ".join(f"{r['control']}={r['verdict']}" for r in st["results"])))
        for r in st["results"]:
            out.append(f"  control {r['control']}: {r['verdict']} ({r['model']}) "
                       + ("; ".join(r["problems"]) or "clean") + f"; gap_ms {r['cut'].get('gap_ms')}")
        out.append("")
    for r in results:
        out += story_lines(r)
    n_pass = sum(1 for r in results if r["verdict"] == "PASS")
    n_fail = sum(1 for r in results if r["verdict"] == "FAIL")
    n_err = sum(1 for r in results if r["verdict"] == "ERROR")
    out.append(f"SUMMARY: {n_pass}/{len(results)} PASS, {n_fail} FAIL, {n_err} ERROR")
    gaps = [r["cut"].get("gap_ms") for r in results if r.get("cut")]
    measured = [g for g in gaps if g is not None]
    if measured:
        out.append(f"gap_ms: measured {len(measured)}/{len(gaps)}, min {min(measured)}, median "
                   f"{sorted(measured)[len(measured) // 2]}")
    for r in results:
        if r["verdict"] in ("FAIL", "ERROR"):
            out.append(f"{r['verdict']} {r['manifest']}:{r['id']}: " + "; ".join(r["problems"]))
    for r in results:
        for w in r.get("warns", []):
            out.append(f"WARN {r['manifest']}:{r['id']}: {w}")
    for nv in not_voiced:
        out.append(f"WARN NOT VOICED {nv['manifest']}:{nv['id']} (listed in the manifest, MP3 404s; the car cannot "
                   f"play it) published {nv['published']} {nv['title']!r}")
    for u in unread:
        out.append(f"UNREAD {u['manifest']}{':' + u['id'] if u.get('id') else ''}: {u['problem']}")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", action="append", default=[])
    ap.add_argument("--cases")
    ap.add_argument("--sample", type=int, help="N newest voiced stories per manifest")
    ap.add_argument("--manifests", help="comma list for --sample (default: every bake.MANIFESTS entry)")
    ap.add_argument("--selftest", action="store_true", help="run the positive controls only")
    ap.add_argument("--fixed-after", help="ISO time or epoch ms; required for --case/--cases")
    ap.add_argument("--out")
    ap.add_argument("--model")
    ap.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    ap.add_argument("--allow-download", action="store_true")
    args = ap.parse_args()
    t_start = time.monotonic()
    sys.stdout.reconfigure(encoding="utf-8")
    lower_priority()
    cases = [parse_case(c) for c in args.case]
    if args.cases:
        with open(args.cases, encoding="utf-8") as f:
            cases += json.load(f)
    if not cases and not args.sample and not args.selftest:
        ap.error("give --sample N, --case/--cases, or --selftest")
    if cases and not args.fixed_after:
        ap.error("--case/--cases need --fixed-after")
    fixed_after = parse_time_ms(args.fixed_after) if args.fixed_after else 0
    mode = "selftest" if (args.selftest and not cases and not args.sample) else ("sample" if args.sample else "cases")
    if args.out:
        prefix = args.out
    elif os.path.isdir(STORE):
        prefix = os.path.join(STORE, "state", "ear", f"ear_{mode}_{time.strftime('%Y%m%d_%H%M%S', time.gmtime())}")
    else:
        ap.error(f"the store {STORE} is not here; pass --out")
    if args.device == "cuda":
        add_cuda_dll_dirs()
    bake = load_bake()
    models = OneModel(args)
    mans = Manifests()
    st = {}
    exit_code = None
    if args.selftest or args.sample:
        ok, st_results, msgs = selftest(bake, models, args)
        st = {"ok": ok, "results": st_results, "messages": msgs}
        print(f"SELFTEST {'PASS' if ok else 'BROKEN'}: " + ("; ".join(msgs) or
              ", ".join(f"{r['control']}={r['verdict']}" for r in st_results)), flush=True)
        if not ok:
            exit_code = 2
    results, not_voiced, unread = [], [], []
    if exit_code is None and args.sample:
        names = args.manifests.split(",") if args.manifests else []
        unknown = set(names) - {m["manifest"] for m in bake.MANIFESTS}
        if unknown:
            ap.error(f"unknown manifest(s) {sorted(unknown)}")
        sc, not_voiced, unread = sample_cases(bake, args.sample, names, mans)
        lang_of = {m["manifest"]: m["lang"] for m in bake.MANIFESTS}
        # one model at a time: every small.en story first, then every tiny story
        cases += sorted(sc, key=lambda c: (args.model or default_model(lang_of[c["manifest"]])) != "small.en")
    if exit_code is None:
        for c in cases:
            try:
                results.append(run_case(c, fixed_after, bake, models, args, mans))
            except Exception as e:
                results.append({"manifest": c.get("manifest"), "id": c.get("id"), "verdict": "ERROR",
                                "problems": [f"{type(e).__name__}: {e}"]})
                if isinstance(e, RuntimeError):   # a ctranslate2/CUDA failure: the next case could hang
                    print(f"stopping after a model error: {e}", file=sys.stderr)
                    break
            r = results[-1]
            print(f"{r['verdict']:5} {r['manifest']}:{r['id']} " + "; ".join(r.get("problems", []) + r.get("warns", [])),
                  flush=True)
    models.close()
    wall = time.monotonic() - t_start
    os.makedirs(os.path.dirname(os.path.abspath(prefix)), exist_ok=True)
    for r in st.get("results", []):
        r.pop("words", None)
    with open(prefix + ".json", "w", encoding="utf-8") as f:
        json.dump({"mode": mode, "fixed_after": iso(fixed_after), "wall_s": round(wall), "selftest": st,
                   "results": results, "not_voiced": not_voiced, "unread": unread}, f, ensure_ascii=False, indent=1)
    rep = text_report(mode, results, fixed_after, st, not_voiced, unread, wall)
    with open(prefix + ".txt", "w", encoding="utf-8") as f:
        f.write(rep + "\n")
    print("\n" + rep)
    print(f"\nwrote {prefix}.json and {prefix}.txt")
    if exit_code is not None:
        return exit_code
    if any(r["verdict"] == "FAIL" for r in results):
        return 1
    if any(r["verdict"] == "ERROR" for r in results):
        return 2
    if (args.sample or cases) and not results:
        print("NOTHING TESTED: a check that tested nothing is not a pass")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
