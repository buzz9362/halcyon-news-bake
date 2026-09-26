"""Sep 26 2026 (JS): no baked text may voice code, and no manifest summary may carry it.

Ear test, circuitly_de rss_1l6c716 (PC-Welt): the car read about 40 s of JavaScript from an affiliate
"sticky promo block" (the worker's stripHtml keeps the text between <script> and </script>). This check
runs the CURRENT text_for + apply_phonetics over real stories (the live manifests on the public R2 base,
or a folder of saved manifest JSON; with --feeds also every manifest's live worker feed) and reports, per
manifest and feed, the summaries that carry code (BROAD, a detector independent of bake.py's anchors),
the ones the rule still leaves in the voiced text, and the stories whose MP3 was voiced with code.

  python tools/code_residue_check.py                        # every manifest in bake.MANIFESTS
  python tools/code_residue_check.py --feeds                # plus every live worker feed
  python tools/code_residue_check.py --dir saved/           # <manifest>.json files saved earlier
  python tools/code_residue_check.py --revoice out.json     # {manifest: [ids]} whose pre-JS voiced text says code
Exit 0 = clean, 1 = code would be voiced or stored, 2 = the check itself is broken (a control failed) or
no story was read. Read-only: GETs public manifests and feeds, never writes R2.
"""
import argparse
import importlib.util
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_BASE = "https://pub-fcb63a0a41b446ea825306ef86fc224f.r2.dev"
UA = {"User-Agent": "halcyon-news-bake code_residue_check"}

# Independent of bake._CR_START on purpose: the two passes must be able to disagree.
BROAD = re.compile(r"[{}]|=>|function\s*\(|(?:document|window)\.[A-Za-z_$]|querySelector|addEventListener|"
                   r"dataLayer|(?<![A-Za-z])(?:var|let|const)\s+[A-Za-z_$][\w$]*\s*=|@media|\d+px\s*;|!important|"
                   r"<\s*/?\s*script")

OWNER_SAMPLE = {
    "id": "rss_1l6c716", "source": "PC-WELT",
    "title": "4 Geräte gleichzeitig laden: USB-C-Netzteil kostet aktuell weniger als 8 Euro",
    "summary": "-15 % 40-Watt-Netzteil günstig bei Amazon Haul Nur 7,64 Euro statt 9,99 Euro UVP Jetzt ansehen "
               "(function () { document.querySelector(\"#sticky-promo-block a\").addEventListener(\"click\", "
               "function(e) { const debug = document.location.host.search(/lndo.site|go-vip.net/)!== -1; const "
               "text = this.closest(\"#sticky-promo-block\").querySelector(\"p.promo-title\").textContent; ret",
}


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


def old_text_for(bake, article):
    """text_for as it was before JS: the summary voiced as strip_social_residue(clean_text()) left it."""
    title = bake.clean_text(article.get("title", ""))
    summary = bake.strip_social_residue(bake.clean_text(article.get("summary", "")))
    source = bake.spoken_source(bake.clean_text(article.get("source", "")))
    parts = [source + ","] if source else []
    if title:
        parts.append(title)
        if not title.endswith((".", "!", "?")):
            parts.append(".")
    if summary and summary.lower() != title.lower():
        parts.append(summary[:bake.FAIR_USE_SNIPPET])
    return " ".join(parts).strip()[:bake.MAX_TEXT_LEN]


def summary_part(bake, article, text):
    """The voiced text after "<source>, <title> ." (a code-like title is not this rule's business)."""
    title = bake.clean_text(article.get("title", ""))
    i = text.find(title)
    return text[i + len(title):] if title and i >= 0 else text


def controls_pass(bake) -> bool:
    if not BROAD.search(summary_part(bake, OWNER_SAMPLE, old_text_for(bake, OWNER_SAMPLE))):
        print("CONTROL FAILED: the pre-JS text of the owner's sample is not flagged")
        return False
    if BROAD.search(summary_part(bake, OWNER_SAMPLE, bake.text_for(OWNER_SAMPLE))):
        print("CONTROL FAILED: text_for still voices the owner's sample code")
        return False
    if BROAD.search(bake.sanitize_article(dict(OWNER_SAMPLE))["summary"]):
        print("CONTROL FAILED: the stored summary of the owner's sample still carries code")
        return False
    prose = "Copilot can make broader changes directly inside a document. Now there is another AI in Word, if (or when) you want it."
    if BROAD.search(prose) or bake.strip_code_residue(prose) is not prose:
        print("CONTROL FAILED: plain prose is flagged or changed")
        return False
    return True


def get_items(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8")).get("items", [])


def read_manifest(name, folder):
    if folder:
        p = os.path.join(folder, name + ".json")
        if not os.path.exists(p):
            return None
        with open(p, encoding="utf-8") as f:
            return json.load(f).get("items", [])
    return get_items(f"{MANIFEST_BASE}/{name}.json")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", help="folder of <manifest>.json files instead of the live R2 manifests")
    ap.add_argument("--feeds", action="store_true", help="also read every manifest's live worker feed")
    ap.add_argument("--revoice", help="write {manifest: [ids]} whose pre-JS voiced text carries code")
    a = ap.parse_args()
    bake = load_bake()
    if not controls_pass(bake):
        return 2
    sources = [("manifest", m, None) for m in bake.MANIFESTS]
    if a.feeds:
        sources += [("feed", m, m["feed_url"]) for m in bake.MANIFESTS]
    read = 0
    voiced_now, stored_now, revoice, rows = [], [], {}, []
    for kind, m, url in sources:
        name = m["manifest"]
        try:
            items = get_items(url) if url else read_manifest(name, a.dir)
        except Exception as e:
            print(f"[{kind}:{name}] unreadable: {e}")
            continue
        if items is None:
            continue
        n = raw_hits = 0
        for art in items:
            if not isinstance(art, dict) or not art.get("id"):
                continue
            n += 1
            summary = art.get("summary") or ""
            if BROAD.search(summary):
                raw_hits += 1
            new = bake.apply_phonetics(bake.text_for(art), m["phonetics"])
            if BROAD.search(summary_part(bake, art, new)):
                voiced_now.append((kind, name, art["id"]))
            if kind == "manifest":
                # What the next pass stores (write_manifest), not what an older pass stored.
                if BROAD.search(bake.without_code_residue(art).get("summary") or ""):
                    stored_now.append((name, art["id"]))
                if BROAD.search(summary_part(bake, art, old_text_for(bake, art))):
                    revoice.setdefault(name, []).append(art["id"])
        read += n
        rows.append((kind, name, n, raw_hits))
    print("# summaries carrying code, per manifest and feed (items, with code)")
    for kind, name, n, h in rows:
        print(f"{kind:8} {name:14} items={n:3d} code={h}")
    print(f"stories read: {read}; summaries with code: {sum(r[3] for r in rows)}; "
          f"voiced with code now: {len(voiced_now)}; stored with code after the next write: {len(stored_now)}; "
          f"MP3s voiced with code (pre-JS text): {sum(len(v) for v in revoice.values())}")
    for kind, name, aid in voiced_now:
        print(f"CODE VOICED [{kind}:{name}] {aid}")
    for name, aid in stored_now:
        print(f"CODE STORED [{name}] {aid}")
    for name, ids in revoice.items():
        print(f"RE-VOICE [{name}] {', '.join(ids)}")
    if a.revoice:
        with open(a.revoice, "w", encoding="utf-8") as f:
            json.dump(revoice, f, indent=1)
        print("wrote", a.revoice)
    if read == 0:
        print("NO STORY READ: a check that read nothing is not a pass")
        return 2
    return 1 if (voiced_now or stored_now) else 0


if __name__ == "__main__":
    sys.exit(main())
