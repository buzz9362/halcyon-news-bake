"""Sep 26 2026 (SX): no baked text may voice a raw social handle.

Owner (Appning car, KPop Today): "LE SSERAFIM's Chaewon | @_chaechae_1/Instagram" was read aloud. This
check runs the CURRENT text_for + apply_phonetics over a sample of real stories (the live manifests on
the public R2 base, or a folder of saved manifest JSON) and fails when any voiced text still carries a
handle (bake.SOCIAL_HANDLE_RE: "@" + name, never the tail of an e-mail address or a URL path).

  python tools/social_handle_check.py                        # every manifest in bake.MANIFESTS
  python tools/social_handle_check.py --dir saved/           # <manifest>.json files saved earlier
  python tools/social_handle_check.py --revoice out.json     # also list the stories whose MP3 in R2
                                                             # (voiced by the pre-SX text_for) says a handle
Exit 0 = clean, 1 = a handle would be voiced, 2 = the check itself is broken (positive control failed)
or no story was read. Read-only: GETs public manifests, never writes R2.
"""
import argparse
import importlib.util
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_BASE = "https://pub-fcb63a0a41b446ea825306ef86fc224f.r2.dev"


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
    """text_for as it was before SX: the summary voiced as clean_text() left it."""
    title = bake.clean_text(article.get("title", ""))
    summary = bake.clean_text(article.get("summary", ""))
    source = bake.spoken_source(bake.clean_text(article.get("source", "")))
    parts = [source + ","] if source else []
    if title:
        parts.append(title)
        if not title.endswith((".", "!", "?")):
            parts.append(".")
    if summary and summary.lower() != title.lower():
        parts.append(summary[:bake.FAIR_USE_SNIPPET])
    return " ".join(parts).strip()[:bake.MAX_TEXT_LEN]


def controls_pass(bake) -> bool:
    bad = {"source": "Koreaboo", "title": "Chaewon post",
           "summary": "It sparked divided reactions. LE SSERAFIM’s Chaewon | @_chaechae_1/Instagram Amid the shows."}
    if not bake.SOCIAL_HANDLE_RE.search(old_text_for(bake, bad)):
        print("CONTROL FAILED: the pre-SX text of the owner's sample is not flagged")
        return False
    if bake.SOCIAL_HANDLE_RE.search(bake.text_for(bad)):
        print("CONTROL FAILED: text_for still voices the owner's sample handle")
        return False
    if bake.SOCIAL_HANDLE_RE.search("mail contato@suaempresa.com.br or Nick Jonas @34"):
        print("CONTROL FAILED: an e-mail address or an age marker is flagged as a handle")
        return False
    return True


def read_manifest(name, folder):
    if folder:
        p = os.path.join(folder, name + ".json")
        if not os.path.exists(p):
            return None
        with open(p, encoding="utf-8") as f:
            return json.load(f).get("items", [])
    req = urllib.request.Request(f"{MANIFEST_BASE}/{name}.json", headers={"User-Agent": "halcyon-news-bake social_handle_check"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8")).get("items", [])


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", help="folder of <manifest>.json files instead of the live R2 manifests")
    ap.add_argument("--revoice", help="write {manifest: [ids]} whose pre-SX voiced text carries a handle")
    a = ap.parse_args()
    bake = load_bake()
    if not controls_pass(bake):
        return 2
    read = 0
    hits = []
    revoice = {}
    changed = {}
    for m in bake.MANIFESTS:
        name = m["manifest"]
        try:
            items = read_manifest(name, a.dir)
        except Exception as e:
            print(f"[{name}] unreadable: {e}")
            continue
        if items is None:
            continue
        for art in items:
            if not isinstance(art, dict) or not art.get("id"):
                continue
            read += 1
            new = bake.apply_phonetics(bake.text_for(art), m["phonetics"])
            if bake.SOCIAL_HANDLE_RE.search(new):
                hits.append((name, art["id"], bake.SOCIAL_HANDLE_RE.search(new).group(0)))
            old = old_text_for(bake, art)
            if bake.SOCIAL_HANDLE_RE.search(old):
                revoice.setdefault(name, []).append(art["id"])
            elif old != bake.text_for(art):
                changed.setdefault(name, []).append(art["id"])
    print(f"stories read: {read}; voiced with a handle now: {len(hits)}; "
          f"pre-SX MP3s that say a handle: {sum(len(v) for v in revoice.values())}; "
          f"other credit or embed lines no longer voiced: {sum(len(v) for v in changed.values())}")
    for name, aid, h in hits:
        print(f"HANDLE VOICED [{name}] {aid} {h}")
    if a.revoice:
        with open(a.revoice, "w", encoding="utf-8") as f:
            json.dump({"handle_in_baked_text": revoice, "credit_line_in_baked_text": changed}, f, indent=1)
        print("wrote", a.revoice)
    if read == 0:
        print("NO STORY READ: a check that read nothing is not a pass")
        return 2
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
