#!/usr/bin/env python3
"""
arxiv_titles.py

Scan one or more arXiv category lists for a specific date and download ONLY
the papers whose TITLES match a list of keywords. Writes JSONL/CSV metadata.
Skips PDFs that already exist in the output folder and avoids duplicates
across categories during the same run.

Keyword matching uses whole-word/phrase boundaries:
  - 'rna' matches "RNA sequencing", but NOT "alteRNAtive"
  - 'cryo-EM' matches the hyphenated phrase as-is
  - matching is case-insensitive

Designed to be imported and called from another script.

Example (from another script):
    from arxiv_titles import get_papers  # or import main (alias)
    result = get_papers(
        date="2025-10-24",
        cats=["cs.LG", "q-bio.BM"],
        keywords=["protein", "rna", "cryo-EM"],
        keyword_mode="any",
        out="./arxiv_TITLES_2025-10-24"
    )
"""

import csv
import json
import os
import re
import sys
import time
from datetime import datetime, date as _date
from zoneinfo import ZoneInfo
from typing import Optional, List, Dict, Set, Tuple, Any, Iterable, Pattern

import requests
from bs4 import BeautifulSoup, Tag

BASE = "https://arxiv.org"
LIST_URL_TPL = "https://arxiv.org/list/{cat}/recent?show=2000"
UA_DEFAULT = "arXiv titles downloader (requests; contact: youremail@example.com)"

# "New submissions for Fri, 24 Oct 2025" style dates
DATE_RE = re.compile(
    r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+(\d{1,2})\s+"
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})"
)
MONTHS = {
    "Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
    "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12
}

ABS_ID_RE = re.compile(r"/abs/([^/?#]+)")
ARXIV_ID_RE = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")  # e.g., 2510.12345v2


# ------------------------- helpers & parsing -------------------------

def _normalize_list(arg: Iterable[str] | str) -> List[str]:
    """
    Accepts either an iterable of strings or a single comma/space-separated string.
    Returns a clean list of non-empty strings.
    """
    if arg is None:
        return []
    if isinstance(arg, str):
        raw = arg
    else:
        raw = " ".join(arg)
    return [t for chunk in raw.split(",") for t in chunk.split() if t]

def _keywords_list(arg: Iterable[str] | str) -> List[str]:
    return [k.strip() for k in _normalize_list(arg)]

def _compile_keyword_patterns(keywords: List[str]) -> List[Pattern]:
    """
    Compile case-insensitive regex patterns that only match a keyword as a whole word/phrase.
    Uses custom "token" boundaries so 'rna' won't match inside 'alteRNAtive'.

    We anchor with (?<![A-Za-z0-9]) ... (?![A-Za-z0-9]) around the escaped keyword.
    """
    pats: List[Pattern] = []
    for kw in keywords:
        if not kw:
            continue
        escaped = re.escape(kw)
        pats.append(re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE))
    return pats

def _target_date(d: _date | str) -> _date:
    if isinstance(d, _date):
        return d
    tz = ZoneInfo("America/New_York")
    try:
        dt = datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=tz)
    except ValueError as e:
        raise ValueError("date must be 'YYYY-MM-DD'") from e
    return dt.date()


# ------------------------- scraping utilities -------------------------

def _find_section_for_date(soup: BeautifulSoup, target_d: _date) -> Optional[Tag]:
    """Find the <h3> whose text contains a date like 'Fri, 24 Oct 2025'."""
    for h3 in soup.find_all("h3"):
        txt = h3.get_text(" ", strip=True)
        m = DATE_RE.search(txt)
        if not m:
            continue
        _, day_str, mon_abbr, year_str = m.groups()
        d = int(day_str); y = int(year_str); mnum = MONTHS[mon_abbr]
        header_date = datetime(y, mnum, d).date()
        if header_date == target_d:
            return h3
    return None

def _iter_entries_between(h3: Tag):
    """Yield (dt, dd) pairs for entries AFTER `h3` up to the NEXT <h3>."""
    next_h3 = h3.find_next("h3")
    dt_pending: Optional[Tag] = None
    for el in h3.next_elements:
        if isinstance(el, Tag) and el is next_h3:
            break
        if not isinstance(el, Tag):
            continue
        if el.name == "dt":
            dt_pending = el
        elif el.name == "dd" and dt_pending is not None:
            yield dt_pending, el
            dt_pending = None

def _extract_abs_id_from_dt(dt_tag: Tag) -> Optional[str]:
    a_abs = dt_tag.select_one('a[title*="Abstract"], a[href^="/abs/"]')
    if a_abs and a_abs.has_attr("href"):
        m = ABS_ID_RE.search(a_abs["href"])
        if m:
            return m.group(1)
    text = dt_tag.get_text(" ", strip=True)
    m = ARXIV_ID_RE.search(text)
    return m.group(0) if m else None

def _extract_title_from_dd(dd_tag: Tag) -> str:
    div = dd_tag.find("div", class_="list-title")
    if not div:
        div = dd_tag.find("div", class_=lambda c: c and "list-title" in c.split())
    if not div:
        return ""
    title = div.get_text(" ", strip=True)
    return re.sub(r"^\s*Title:\s*", "", title)

def _extract_subjects_text(dd_tag: Tag) -> str:
    subj_div = dd_tag.find("div", class_="list-subjects")
    return subj_div.get_text(" ", strip=True) if subj_div else ""


# ------------------------- metadata & download -------------------------

def _extract_pdf_url_from_id(abs_id: str) -> str:
    url = f"{BASE}/pdf/{abs_id}"
    return url if url.endswith(".pdf") else url + ".pdf"

def _sanitize_filename(url: str) -> str:
    name = url.split("/pdf/")[-1].split("?")[0]
    if not name.endswith(".pdf"):
        name += ".pdf"
    name = re.sub(r"[^A-Za-z0-9.\-_]+", "_", name)
    if not name.lower().startswith("arxiv-"):
        name = f"arXiv-{name}"
    return name

def _download_pdf(url: str, out_dir: str, session: requests.Session) -> Optional[str]:
    os.makedirs(out_dir, exist_ok=True)
    fn = _sanitize_filename(url)
    path = os.path.join(out_dir, fn)
    if os.path.exists(path):
        print(f"⏭ Skip (exists): {fn}")
        return path
    with session.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        size_msg = f" ({total/1024/1024:.2f} MB)" if total else ""
        print(f"↓ Downloading: {fn}{size_msg}")
        with open(path, "wb") as f:
            for chunk in r.iter_content(chunk_size=131072):
                if chunk:
                    f.write(chunk)
    print(f"✓ Saved: {fn}")
    return path

def _fetch_abs_metadata(abs_id: str, session: requests.Session) -> Dict[str, Any]:
    """Fetch title, authors, abstract, and submitted date from /abs/<id>."""
    abs_url = f"{BASE}/abs/{abs_id}"
    r = session.get(abs_url, timeout=60)
    r.raise_for_status()
    s = BeautifulSoup(r.text, "html.parser")

    # Title
    title = None
    mt = s.select_one('meta[name="citation_title"]')
    if mt and mt.get("content"):
        title = mt["content"].strip()
    if not title:
        h1 = s.select_one("h1.title")
        if h1:
            title = re.sub(r"^\s*Title:\s*", "", h1.get_text(" ", strip=True))

    # Authors
    authors = [m["content"].strip() for m in s.select('meta[name="citation_author"]') if m.get("content")]
    if not authors:
        auth_div = s.select_one("div.authors")
        if auth_div:
            authors = [a.get_text(strip=True) for a in auth_div.select("a")]

    # Abstract
    abstract = None
    bq = s.select_one("blockquote.abstract")
    if bq:
        abstract = re.sub(r"^\s*Abstract:\s*", "", bq.get_text(" ", strip=True))

    # Submitted date
    submitted = None
    dl = s.select_one("div.dateline")
    if dl:
        submitted = dl.get_text(" ", strip=True)

    mver = ARXIV_ID_RE.match(abs_id)
    version = mver.group(2) if mver else None

    return {
        "arxiv_id": mver.group(1) if mver else abs_id,
        "version": version,
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "submitted": submitted,
        "abs_url": abs_url,
        "pdf_url": _extract_pdf_url_from_id(abs_id),
    }

def _write_metadata(out_dir: str, rows: List[Dict[str, Any]]) -> None:
    os.makedirs(out_dir, exist_ok=True)
    jsonl_path = os.path.join(out_dir, "metadata.jsonl")
    csv_path = os.path.join(out_dir, "metadata.csv")

    with open(jsonl_path, "w", encoding="utf-8") as jf:
        for r in rows:
            jf.write(json.dumps(r, ensure_ascii=False) + "\n")

    fieldnames = [
        "arxiv_id", "version", "title", "authors", "abstract",
        "submitted", "abs_url", "pdf_url", "pdf_path", "source_category", "subjects"
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as cf:
        w = csv.DictWriter(cf, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            r_flat = r.copy()
            r_flat["authors"] = "; ".join(r.get("authors") or [])
            w.writerow(r_flat)

    print(f"✓ Wrote metadata:\n  - {jsonl_path}\n  - {csv_path}")


# ------------------------- per-category processing -------------------------

def _process_category(
    session: requests.Session,
    category: str,
    tdate: _date,
    out_dir: str,
    kw_patterns: List[Pattern],
    keyword_mode: str,
    seen_ids: Set[str],
    sleep: float = 0.0,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    list_url = LIST_URL_TPL.format(cat=category)
    label = category
    print(f"[{label}] Fetching listing: {list_url}")
    html = session.get(list_url, timeout=60)
    html.raise_for_status()
    soup = BeautifulSoup(html.text, "html.parser")

    h3 = _find_section_for_date(soup, tdate)
    if not h3:
        available = []
        for tag in soup.find_all("h3"):
            m = DATE_RE.search(tag.get_text(" ", strip=True))
            if m:
                _, d, mon, y = m.groups()
                available.append(f"{int(d):02d} {mon} {y}")
        print(f"[{label}] No section found for: {tdate} (America/New_York).")
        if available:
            print(f"[{label}] Available dates on page: " + ", ".join(available))
        return [], {"scanned": 0, "matched": 0, "skipped_existing": 0, "skipped_duplicate": 0}

    def _title_matches_patterns(title: str) -> bool:
        if not kw_patterns:
            return True
        if keyword_mode == "all":
            return all(p.search(title) for p in kw_patterns)
        return any(p.search(title) for p in kw_patterns)

    rows: List[Dict[str, Any]] = []
    scanned = 0
    matched = 0
    skipped_existing = 0
    skipped_duplicate = 0

    for dt_tag, dd_tag in _iter_entries_between(h3):
        scanned += 1
        title = _extract_title_from_dd(dd_tag)
        if not title or not _title_matches_patterns(title):
            continue

        abs_id = _extract_abs_id_from_dt(dt_tag)
        if not abs_id:
            continue

        base_id = ARXIV_ID_RE.match(abs_id).group(1) if ARXIV_ID_RE.match(abs_id) else abs_id
        if base_id in seen_ids:
            print(f"[{label}] ⏭ Skip (duplicate id in this run): {base_id}")
            skipped_duplicate += 1
            continue
        seen_ids.add(base_id)

        pdf_url = _extract_pdf_url_from_id(abs_id)
        pdf_fn = _sanitize_filename(pdf_url)
        pdf_path_expected = os.path.join(out_dir, pdf_fn)
        if os.path.exists(pdf_path_expected):
            print(f"[{label}] ⏭ Skip (exists): {pdf_fn}")
            skipped_existing += 1
            continue

        # Fetch metadata and download
        try:
            meta = _fetch_abs_metadata(abs_id, session)
        except Exception as e:
            print(f"[{label}] ✗ Metadata fetch failed for {abs_id}: {e}", file=sys.stderr)
            meta = {
                "arxiv_id": base_id,
                "version": None,
                "title": title,
                "authors": [],
                "abstract": None,
                "submitted": None,
                "abs_url": f"{BASE}/abs/{abs_id}",
                "pdf_url": pdf_url,
            }

        try:
            pdf_path = _download_pdf(meta["pdf_url"], out_dir, session)
        except Exception as e:
            print(f"[{label}] ✗ PDF download failed for {abs_id}: {e}", file=sys.stderr)
            pdf_path = None

        subjects_line = _extract_subjects_text(dd_tag)
        rows.append({
            **meta,
            "pdf_path": pdf_path,
            "source_category": category,
            "subjects": subjects_line,
        })
        matched += 1

        if sleep > 0:
            time.sleep(sleep)

    stats = {
        "scanned": scanned,
        "matched": matched,
        "skipped_existing": skipped_existing,
        "skipped_duplicate": skipped_duplicate,
    }
    return rows, stats


# ------------------------- public API -------------------------

def get_papers(
    date: _date | str,
    cats: Iterable[str] | str,
    keywords: Iterable[str] | str,
    out: Optional[str] = None,
    keyword_mode: str = "any",
    sleep: float = 0.0,
    user_agent: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run the downloader.

    Args:
        date: target date (YYYY-MM-DD string or datetime.date), America/New_York.
        cats: iterable or string of arXiv categories, e.g. ["cs.LG", "q-bio.BM"] or "cs.LG,q-bio.BM".
        keywords: iterable or string of title keywords; whole-word/phrase, case-insensitive.
        out: output folder; default: ./arxiv_TITLES_<YYYY-MM-DD>.
        keyword_mode: "any" (default) or "all".
        sleep: seconds between downloads (politeness).
        user_agent: optional UA string for requests.

    Returns:
        {
          "out_dir": <str>,
          "rows": <list of metadata dicts>,
          "per_category": { "<cat>": {stats...}, ... }
        }
    """
    if keyword_mode not in ("any", "all"):
        raise ValueError("keyword_mode must be 'any' or 'all'")

    tdate = _target_date(date)
    cats_list = _normalize_list(cats)
    kw_list = _keywords_list(keywords)
    if not cats_list:
        raise ValueError("--cats produced an empty list")
    if not kw_list:
        raise ValueError("--keywords produced an empty list")

    # Compile once so boundaries are enforced consistently across categories.
    kw_patterns = _compile_keyword_patterns(kw_list)

    out_dir = out or f"arxiv_TITLES_{tdate.isoformat()}"
    os.makedirs(out_dir, exist_ok=True)
    print(f"Categories: {cats_list}")
    print(f"Keywords ({keyword_mode}): {kw_list}")
    print(f"Destination: {os.path.abspath(out_dir)}")

    sess = requests.Session()
    sess.headers.update({"User-Agent": user_agent or UA_DEFAULT})

    all_rows: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()
    per_cat_stats: Dict[str, Dict[str, int]] = {}

    for cat in cats_list:
        rows, stats = _process_category(
            session=sess,
            category=cat,
            tdate=tdate,
            out_dir=out_dir,
            kw_patterns=kw_patterns,
            keyword_mode=keyword_mode,
            seen_ids=seen_ids,
            sleep=sleep,
        )
        per_cat_stats[cat] = stats
        all_rows.extend(rows)
        print(
            f"[{cat}] New: {len(rows)} (matched {stats['matched']} / scanned {stats['scanned']}; "
            f"skipped {stats['skipped_existing']} existing, {stats['skipped_duplicate']} duplicates)"
        )

    if not all_rows:
        print("No new entries downloaded.")
        return {"out_dir": out_dir, "rows": [], "per_category": per_cat_stats}

    _write_metadata(out_dir, all_rows)
    print("Done.")
    return {"out_dir": out_dir, "rows": all_rows, "per_category": per_cat_stats}


# Backward-compatible alias (some code imports `main`)
def main(**kwargs):
    return get_papers(**kwargs)


__all__ = ["get_papers", "main"]
