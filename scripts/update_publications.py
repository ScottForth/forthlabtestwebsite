#!/usr/bin/env python3
"""
Refresh publications.json from a Google Scholar profile.

Google Scholar has no official API and blocks most automated traffic, so this
script tries two sources in order:

  1. SerpApi's Google Scholar Author API (reliable; needs SERPAPI_KEY).
     The free SerpApi plan (250 searches/month) is far more than a weekly
     update needs: one search per 100 publications.
  2. Direct fetch of the Scholar profile page (no key, but Scholar often
     answers cloud servers with a robot check, so expect it to fail at times).

If both fail, the existing publications.json is left untouched, so the
website never goes blank.

Usage:
    SERPAPI_KEY=... python scripts/update_publications.py
    python scripts/update_publications.py --out publications.json --author Efwi0VsAAAAJ
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

AUTHOR_ID = "Efwi0VsAAAAJ"
SCHOLAR = "https://scholar.google.com"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def cites_id(url: str | None) -> str | None:
    """Pull the 'cites=' cluster id out of a Scholar 'Cited by' link."""
    m = re.search(r"cites=([\d,]+)", url or "")
    return m.group(1) if m else None


def profile_url(author_id: str) -> str:
    return f"{SCHOLAR}/citations?user={author_id}&hl=en&sortby=pubdate"


# --------------------------------------------------------------------------- #
# Source 1: SerpApi
# --------------------------------------------------------------------------- #
def fetch_serpapi(author_id: str, key: str) -> dict:
    articles, profile, metrics = [], {}, {}
    start = 0
    while True:
        r = requests.get(
            "https://serpapi.com/search.json",
            params={
                "engine": "google_scholar_author",
                "author_id": author_id,
                "hl": "en",
                "sort": "pubdate",
                "num": 100,
                "start": start,
                "api_key": key,
            },
            timeout=60,
        )
        r.raise_for_status()
        d = r.json()
        if "error" in d:
            raise RuntimeError(f"SerpApi: {d['error']}")

        if start == 0:
            a = d.get("author", {})
            profile = {"name": a.get("name"), "affiliation": a.get("affiliations")}
            for row in d.get("cited_by", {}).get("table", []):
                if "citations" in row:
                    metrics["citations"] = row["citations"].get("all")
                elif "h_index" in row:
                    metrics["h_index"] = row["h_index"].get("all")
                elif "i10_index" in row:
                    metrics["i10_index"] = row["i10_index"].get("all")

        page = d.get("articles", [])
        for it in page:
            cb = it.get("cited_by") or {}
            articles.append(
                {
                    "title": it.get("title", "").strip(),
                    "authors": it.get("authors", "").strip(),
                    "venue": it.get("publication", "").strip(),
                    "year": str(it.get("year") or "").strip(),
                    "cited_by": cb.get("value") or 0,
                    "cites_id": cites_id(cb.get("link")),
                    "id": it.get("citation_id"),
                }
            )
        if len(page) < 100 or not d.get("serpapi_pagination", {}).get("next"):
            break
        start += 100
    return {"profile": profile, "metrics": metrics, "articles": articles}


# --------------------------------------------------------------------------- #
# Source 2: direct Scholar page
# --------------------------------------------------------------------------- #
def fetch_direct(author_id: str) -> dict:
    from bs4 import BeautifulSoup  # imported here so SerpApi-only runs don't need it

    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    articles, profile, metrics = [], {}, {}
    cstart = 0
    while True:
        r = s.get(
            f"{SCHOLAR}/citations",
            params={"user": author_id, "hl": "en", "sortby": "pubdate", "cstart": cstart, "pagesize": 100},
            timeout=60,
        )
        if r.status_code != 200 or "gsc_a_tr" not in r.text and cstart == 0:
            raise RuntimeError(f"Scholar returned HTTP {r.status_code} (likely a robot check)")
        soup = BeautifulSoup(r.text, "html.parser")

        if cstart == 0:
            name = soup.select_one("#gsc_prf_in")
            aff = soup.select_one(".gsc_prf_il")
            profile = {"name": name and name.get_text(strip=True), "affiliation": aff and aff.get_text(strip=True)}
            cells = [c.get_text(strip=True) for c in soup.select("#gsc_rsb_st td.gsc_rsb_std")]
            if len(cells) >= 6:
                metrics = {"citations": int(cells[0]), "h_index": int(cells[2]), "i10_index": int(cells[4])}

        rows = soup.select("tr.gsc_a_tr")
        for row in rows:
            a = row.select_one("a.gsc_a_at")
            gray = row.select(".gs_gray")
            venue = gray[1].get_text(" ", strip=True) if len(gray) > 1 else ""
            venue = re.sub(r",\s*\d{4}$", "", venue)  # Scholar appends ", YEAR"
            cites_a = row.select_one(".gsc_a_c a")
            cites = cites_a.get_text(strip=True) if cites_a else ""
            href = a.get("href") if a else None
            articles.append(
                {
                    "title": a.get_text(strip=True) if a else "",
                    "authors": gray[0].get_text(strip=True) if gray else "",
                    "venue": venue,
                    "year": (row.select_one(".gsc_a_y span") or row.select_one(".gsc_a_y")).get_text(strip=True),
                    "cited_by": int(cites) if cites.isdigit() else 0,
                    "cites_id": cites_id(cites_a.get("href") if cites_a else None),
                    "id": (re.search(r"citation_for_view=([^&]+)", href or "") or [None, None])[1],
                }
            )
        if len(rows) < 100:
            break
        cstart += 100
        time.sleep(3)
    if not articles:
        raise RuntimeError("Scholar page had no publications (likely a robot check)")
    return {"profile": profile, "metrics": metrics, "articles": articles}


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--author", default=os.environ.get("SCHOLAR_AUTHOR_ID", AUTHOR_ID))
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "publications.json"))
    args = ap.parse_args()

    out = Path(args.out)
    old = json.loads(out.read_text()) if out.exists() else {}

    data, errors = None, []
    key = os.environ.get("SERPAPI_KEY")
    sources = ([("SerpApi", lambda: fetch_serpapi(args.author, key))] if key else []) + [
        ("Google Scholar (direct)", lambda: fetch_direct(args.author))
    ]
    for name, fn in sources:
        try:
            data = fn()
            print(f"✓ {name}: {len(data['articles'])} publications")
            data["source"] = name
            break
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {e}")
            print(f"✗ {name}: {e}", file=sys.stderr)

    if data is None:
        print("No source succeeded; keeping existing publications.json.", file=sys.stderr)
        return 1

    # Guard against a partial/blocked response wiping out the list.
    if old.get("articles") and len(data["articles"]) < 0.8 * len(old["articles"]):
        print(
            f"Refusing to overwrite: got {len(data['articles'])} items vs {len(old['articles'])} before.",
            file=sys.stderr,
        )
        return 1

    data["profile"]["url"] = profile_url(args.author)
    data["profile"]["author_id"] = args.author

    # Only bump the timestamp when something actually changed, so the scheduled
    # job doesn't create an empty commit every week.
    comparable = lambda d: json.dumps({k: d.get(k) for k in ("profile", "metrics", "articles")}, sort_keys=True)
    if old and comparable(old) == comparable(data):
        print("No changes.")
        return 0

    data["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ordered = {k: data[k] for k in ("updated", "source", "profile", "metrics", "articles")}
    out.write_text(json.dumps(ordered, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
