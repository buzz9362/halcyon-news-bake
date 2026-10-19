"""r1019 N2-18: hashtag_keep.json is generated from the news apps' search dictionaries (one source).

Each news app keeps its search dictionary in app/src/main/java/<pkg>/data/SearchDictionary.kt. The apps'
splitTitleHashtags keeps a single title hashtag whose lower-case form is a dictionary term ("#NewJeans"
stays "NewJeans"); bake.py split_single_hashtags applies the same keep list from hashtag_keep.json, keyed
by the app prefix of a manifest's phonetics key (kpop_en -> kpop). This tool writes or checks that file.

  python tools/sync_hashtag_keep.py --check   # exit 1 when hashtag_keep.json differs from the apps
  python tools/sync_hashtag_keep.py --write   # regenerate hashtag_keep.json from the apps
  --apps-root <dir> (default: ../App Market Submission next to this repo)
"""
import argparse
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "hashtag_keep.json")
DEFAULT_APPS_ROOT = os.path.join(os.path.dirname(ROOT), "App Market Submission")
# baker app key (prefix of the phonetics key) -> app directory
APPS = {
    "anime": "anime-brief-app", "bollywood": "bollywood-today-app", "circuitly": "circuitly-app",
    "hype": "hype-id-app", "kpop": "kpop-today-app", "tropic": "kpop-tropic-app",
    "tickerly": "tickerly-app", "tinh": "tinh-tu-app",
}


def dictionary_terms(apps_root: str, app_dir: str) -> list:
    hits = glob.glob(os.path.join(apps_root, app_dir, "app", "src", "main", "java", "**", "data", "SearchDictionary.kt"),
                     recursive=True)
    if len(hits) != 1:
        raise SystemExit(f"{app_dir}: expected one data/SearchDictionary.kt, found {len(hits)}")
    src = open(hits[0], encoding="utf-8").read().split("internal val HASHTAG_KEEP_LOWER")[0]
    terms = []
    for body in re.findall(r"internal val \w+ = listOf\((.*?)\n\)", src, re.S):
        body = "\n".join(l for l in body.split("\n") if not l.strip().startswith("//"))
        for lit in re.findall(r'"((?:[^"\\]|\\.)*)"', body):
            if "\\" in lit:
                raise SystemExit(f"{app_dir}: escaped literal not supported: {lit!r}")
            terms.append(lit)
    if not terms:
        raise SystemExit(f"{app_dir}: no dictionary terms read")
    return terms


def build(apps_root: str) -> dict:
    # Kotlin String.lowercase() is Locale.ROOT; str.lower() matches it for these (Latin + Devanagari) terms.
    return {key: sorted({t.lower() for t in dictionary_terms(apps_root, d)}) for key, d in APPS.items()}


def dump(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--write", action="store_true")
    ap.add_argument("--apps-root", default=DEFAULT_APPS_ROOT)
    a = ap.parse_args()
    want = dump(build(a.apps_root))
    if a.write:
        with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(want)
        print(f"wrote {OUT}")
        return 0
    have = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
    if have != want:
        print("hashtag_keep.json differs from the apps' data/SearchDictionary.kt; run --write")
        return 1
    print("hashtag_keep.json matches the apps")
    return 0


if __name__ == "__main__":
    sys.exit(main())
