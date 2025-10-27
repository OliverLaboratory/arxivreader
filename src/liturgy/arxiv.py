#!/usr/bin/env python3
"""
Download arXiv PDFs for a specific date from the q-bio listing (default),
keeping only papers whose topic tags (e.g., q-bio.BM cs.LG) are a SUBSET
of a user-defined allowed tag set. Also (optionally) fetch from the cs.LG
listing for the same date, but ONLY include papers whose TITLE contains
user-specified keywords. Save metadata for downloaded items.

Skips any paper whose PDF already exists in the destination folder and prints a message.
Also avoids processing the same arXiv ID twice when it appears in both lists.

Examples:
  pip install requests beautifulsoup4
  python arxiv_subset.py --date 2025-10-24 --allow-tags q-bio.BM,cs.LG --out ./arxiv_2025-10-24_subset
  python arxiv_subset.py --date 2025-10-24 --allow-tags "q-bio.BM cs.LG" --sleep 0.5
  python arxiv_subset.py --date 2025-10-24 --allow-tags q-bio.BM,cs.LG --include-cs-lg --cs-keywords "biology protein"
  python arxiv_subset.py --date 2025-10-24 --allow-tags q-bio.BM,cs.LG --include-cs-lg --cs-keywords ml,biology,sequence --keyword-mode any
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, List, Dict, Set, Tuple

import requests
from bs4 import BeautifulSoup, Tag

BASE = "https://arxiv.org"
LIST_URL_QBIO = "https://arxiv.org/list/q-bio/recent?show=2000"
LIST_URL_CS_LG = "https://arxiv.org/list/cs.LG/recent?show=2000"
UA = "arXiv q-bio/cs.LG downloader (requests; contact: youremail@example.com)"

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
TAG_CODE_RE = re.compile(r"\(([A-Za-z0-9.\-]+)\)")     # e.g., (q-bio.BM), (cs.LG)

def parse_args():
    p = argparse.ArgumentParser(
        description=(
            "Download arXiv PDFs for a given date with tag-subset filtering. "
            "Optionally also fetch from cs.LG if title contains given keywords. "
            "Skips already-downloaded PDFs."
        )
    )
    p.add_argument("--date", required=True, help="Target date YYYY-MM-DD (America/New_York)")
    p.add_argument("--out", default=None, help="Output folder (default: ./arxiv_SUBSET_YYYY-MM-DD)")
    p.add_argument(
        "--allow-tags",
        required=True,
        nargs="+",
        help="Allowed tag codes (space- or comma-separated), e.g.: q-bio.BM cs.LG stat.ML"
    )
    p.add_argument(
        "--include-cs-lg",
        action="store_true",
        help="Also fetch from the cs.LG listing (for the same date). Requires --cs-keywords."
    )
    p.add_argument(
        "--cs-keywords",
        nargs="+",
        default=None,
        help="Keywords for filtering cs.LG titles (space- or comma-separated)."
    )
    p.add_argument(
        "--keyword-mode",
        choices=["any", "all"],
        default="any",
        help="For cs.LG titles: require ANY keyword (default) or ALL keywords."
    )
    p.add_argument("--sleep", type=float, default=0.0, help="Seconds to sleep between metadata fetches (politeness)")
    return p.parse_args()

def parse_allowed_tags(tokens: List[str]) -> Set[str]:
    """Split on commas and whitespace, normalize, and return a set of tag codes."""
    raw = " ".join(tokens)
    parts = [t.strip() for chunk in raw.split(",") for t in chunk.split()]
    return {p for p in parts if p}

def parse_keywords(tokens: Optional[List[str]]) -> List[str]:
    if not tokens:
        return []
    raw = " ".join(tokens)
    parts = [t.strip() for chunk in raw.split(",") for t in chunk.split()]
    # Drop empties, lowercase for case-insensitive matching
    return [p.lower() for p in parts if p]

def target_date(date_str: str):
    tz = ZoneInfo("America/New_York")
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=tz)
    except ValueError:
        print("Error: --date must be YYYY-MM-DD", file=sys.stderr)
        sys.exit(2)
    return dt.date()

def find_section_for_date(soup: BeautifulSoup, target_d):
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

def iter_entries_between(h3: Tag):
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

def extract_abs_id_from_dt(dt_tag: Tag) -> Optional[str]:
    """Return arXiv abs id like '2510.12345v2' or '2510.12345' from the <dt>."""
    a_abs = dt_tag.select_one('a[title*="Abstract"], a[href^="/abs/"]')
    if a_abs and a_abs.has_attr("href"):
        m = ABS_ID_RE.search(a_abs["href"])
        if m:
            return m.group(1)
    text = dt_tag.get_text(" ", strip=True)
    m = ARXIV_ID_RE.search(text)
    return m.group(0) if m else None

def extract_subjects_text(dd_tag: Tag) -> str:
    subj_div = dd_tag.find("div", class_="list-subjects")
    return subj_div.get_text(" ", strip=True) if subj_div else ""

def parse_tag_codes(subjects_text: str) -> List[str]:
    """From 'Subjects: X (q-bio.BM); Y (cs.LG)' extract ['q-bio.BM', 'cs.LG']."""
    return TAG_CODE_RE.findall(subjects_text or "")

def extract_title_from_dd(dd_tag: Tag) -> str:
    """
    Extract the title text from the listing dd. Usually in:
      <div class="list-title mathjax">Title: ...</div>
    """
    div = dd_tag.find("div", class_="list-title")
    if not div:
        # Sometimes class has two tokens e.g., 'list-title mathjax'
        div = dd_tag.find("div", class_=lambda c: c and "list-title" in c.split())
    if not div:
        return ""
    title = div.get_text(" ", strip=True)
    title = re.sub(r"^\s*Title:\s*", "", title)
    return title

def title_matches(title: str, keywords: List[str], mode: str = "any") -> bool:
    if not keywords:
        return True
    t = title.lower()
    if mode == "all":
        return all(k in t for k in keywords)
    return any(k in t for k in keywords)

def entry_tags_subset(dd_tag: Tag, allowed: Set[str]) -> bool:
    """Keep the paper iff all of its tag codes are contained in `allowed`."""
    codes = parse_tag_codes(extract_subjects_text(dd_tag))
    if not codes:
        return False  # be conservative if parsing failed
    return set(codes).issubset(allowed)

def extract_pdf_url_from_id(abs_id: str) -> str:
    url = f"{BASE}/pdf/{abs_id}"
    return url if url.endswith(".pdf") else url + ".pdf"

def sanitize_filename(url: str) -> str:
    name = url.split("/pdf/")[-1].split("?")[0]
    if not name.endswith(".pdf"):
        name += ".pdf"
    name = re.sub(r"[^A-Za-z0-9.\-_]+", "_", name)
    if not name.lower().startswith("arxiv-"):
        name = f"arXiv-{name}"
    return name

def download_pdf(url: str, out_dir: str, session: requests.Session) -> Optional[str]:
    os.makedirs(out_dir, exist_ok=True)
    fn = sanitize_filename(url)
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

def fetch_abs_metadata(abs_id: str, session: requests.Session) -> Dict:
    """Fetch title, authors, abstract, submitted date, and (redundantly) tags from /abs/<id>."""
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

    # Version (e.g., v2) if present
    version = None
    mver = ARXIV_ID_RE.match(abs_id)
    if mver:
        version = mver.group(2)  # may be None

    # Subjects/tags from the abs page (redundant but more robust)
    subj_text = ""
    subj_block = s.select_one("td.tablecell.subjects, div.metatable > span.primary-subject")
    if not subj_block:
        subj_block = s.find("td", class_="tablecell subjects")
    if subj_block:
        subj_text = subj_block.get_text(" ", strip=True)
    tags_from_abs = parse_tag_codes(subj_text)

    return {
        "arxiv_id": mver.group(1) if mver else abs_id,
        "version": version,
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "submitted": submitted,
        "abs_url": abs_url,
        "pdf_url": extract_pdf_url_from_id(abs_id),
        "tags_abs": tags_from_abs,
    }

def write_metadata(out_dir: str, rows: List[Dict]):
    os.makedirs(out_dir, exist_ok=True)
    jsonl_path = os.path.join(out_dir, "metadata.jsonl")
    csv_path = os.path.join(out_dir, "metadata.csv")

    # JSONL
    with open(jsonl_path, "w", encoding="utf-8") as jf:
        for r in rows:
            jf.write(json.dumps(r, ensure_ascii=False) + "\n")

    # CSV (flatten authors/tags as semicolon-separated)
    fieldnames = [
        "arxiv_id", "version", "title", "authors", "abstract",
        "subjects", "tags_listed", "tags_abs",
        "submitted", "abs_url", "pdf_url", "pdf_path"
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as cf:
        w = csv.DictWriter(cf, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            r_flat = r.copy()
            r_flat["authors"] = "; ".join(r.get("authors") or [])
            r_flat["tags_listed"] = "; ".join(r.get("tags_listed") or [])
            r_flat["tags_abs"] = "; ".join(r.get("tags_abs") or [])
            w.writerow(r_flat)

    print(f"✓ Wrote metadata:\n  - {jsonl_path}\n  - {csv_path}")

def process_listing(
    session: requests.Session,
    list_url: str,
    tdate,
    allowed: Set[str],
    out_dir: str,
    sleep: float = 0.0,
    title_keywords: Optional[List[str]] = None,
    keyword_mode: str = "any",
    seen_ids: Optional[Set[str]] = None,
    label: str = "listing",
) -> Tuple[List[Dict], Dict[str, int]]:
    """
    Generic processor for a single listing URL (q-bio or cs.LG).
    Applies allowed-tag subset filter. Optionally applies title keyword filter.
    Returns (rows, stats).
    """
    print(f"[{label}] Fetching listing: {list_url}")
    html = session.get(list_url, timeout=60)
    html.raise_for_status()
    soup = BeautifulSoup(html.text, "html.parser")

    h3 = find_section_for_date(soup, tdate)
    if not h3:
        # Show which dates ARE available to help debugging
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

    rows: List[Dict] = []
    total_entries = 0
    matched_entries = 0
    skipped_existing = 0
    skipped_duplicate = 0

    for dt_tag, dd_tag in iter_entries_between(h3):
        total_entries += 1

        # Tag subset filter
        if not entry_tags_subset(dd_tag, allowed):
            continue

        # Title keyword filter (if provided)
        if title_keywords is not None:
            title = extract_title_from_dd(dd_tag)
            if not title_matches(title, title_keywords, keyword_mode):
                continue

        matched_entries += 1

        abs_id = extract_abs_id_from_dt(dt_tag)
        if not abs_id:
            continue

        # Deduplicate across sources within this run
        if seen_ids is not None:
            base_id = ARXIV_ID_RE.match(abs_id).group(1) if ARXIV_ID_RE.match(abs_id) else abs_id
            if base_id in seen_ids:
                print(f"[{label}] ⏭ Skip (duplicate id in this run): {base_id}")
                skipped_duplicate += 1
                continue
            seen_ids.add(base_id)

        # Early skip if the expected PDF already exists
        pdf_url = extract_pdf_url_from_id(abs_id)
        pdf_fn = sanitize_filename(pdf_url)
        pdf_path_expected = os.path.join(out_dir, pdf_fn)
        if os.path.exists(pdf_path_expected):
            print(f"[{label}] ⏭ Skip (exists): {pdf_fn}")
            skipped_existing += 1
            continue

        # Fetch metadata
        try:
            meta = fetch_abs_metadata(abs_id, session)
        except Exception as e:
            print(f"[{label}] ✗ Metadata fetch failed for {abs_id}: {e}", file=sys.stderr)
            meta = {
                "arxiv_id": abs_id,
                "version": None,
                "title": None,
                "authors": [],
                "abstract": None,
                "submitted": None,
                "abs_url": f"{BASE}/abs/{abs_id}",
                "pdf_url": pdf_url,
                "tags_abs": [],
            }

        # Download PDF (function also guards against duplicates)
        try:
            pdf_path = download_pdf(meta["pdf_url"], out_dir, session)
        except Exception as e:
            print(f"[{label}] ✗ PDF download failed for {abs_id}: {e}", file=sys.stderr)
            pdf_path = None

        subjects_line = extract_subjects_text(dd_tag)
        row = {
            **meta,
            "subjects": subjects_line,
            "tags_listed": parse_tag_codes(subjects_line),
            "pdf_path": pdf_path,
        }
        rows.append(row)

        if sleep > 0:
            time.sleep(sleep)

    stats = {
        "scanned": total_entries,
        "matched": matched_entries,
        "skipped_existing": skipped_existing,
        "skipped_duplicate": skipped_duplicate,
    }
    return rows, stats

def get_papers(
    date: str,
    allowed_tags: Set[str],
    out_dir: Optional[str],
    sleep=0.0,
    include_cs_lg: bool = False,
    cs_keywords: Optional[List[str]] = None,
    keyword_mode: str = "any",
):
    tdate = target_date(date)
    allow = set(allowed_tags)
    if not allow:
        print("Error: --allow-tags produced an empty set.", file=sys.stderr)
        sys.exit(2)

    if include_cs_lg and not cs_keywords:
        print("Error: --include-cs-lg requires --cs-keywords.", file=sys.stderr)
        sys.exit(2)

    if not out_dir:
        out_dir = f"arxiv_SUBSET_{tdate.isoformat()}"
    os.makedirs(out_dir, exist_ok=True)

    print(f"Allowed tags (subset filter): {sorted(allow)}")
    print(f"Destination: {os.path.abspath(out_dir)}")

    sess = requests.Session()
    sess.headers.update({"User-Agent": UA})

    seen_ids: Set[str] = set()
    all_rows: List[Dict] = []

    # q-bio listing (always)
    qbio_rows, qbio_stats = process_listing(
        session=sess,
        list_url=LIST_URL_QBIO,
        tdate=tdate,
        allowed=allow,
        out_dir=out_dir,
        sleep=sleep,
        title_keywords=None,          # no title restriction for q-bio
        keyword_mode="any",
        seen_ids=seen_ids,
        label="q-bio",
    )
    all_rows.extend(qbio_rows)
    print(
        f"[q-bio] Found {len(qbio_rows)} new entry(ies) for {tdate} "
        f"(matched {qbio_stats['matched']} / scanned {qbio_stats['scanned']}; "
        f"skipped {qbio_stats['skipped_existing']} existing, {qbio_stats['skipped_duplicate']} duplicates)."
    )

    # cs.LG listing (optional; title keyword filter)
    if include_cs_lg:
        cs_rows, cs_stats = process_listing(
            session=sess,
            list_url=LIST_URL_CS_LG,
            tdate=tdate,
            allowed=allow,
            out_dir=out_dir,
            sleep=sleep,
            title_keywords=cs_keywords,
            keyword_mode=keyword_mode,
            seen_ids=seen_ids,
            label="cs.LG",
        )
        all_rows.extend(cs_rows)
        print(
            f"[cs.LG] Found {len(cs_rows)} new entry(ies) for {tdate} "
            f"(matched {cs_stats['matched']} / scanned {cs_stats['scanned']}; "
            f"skipped {cs_stats['skipped_existing']} existing, {cs_stats['skipped_duplicate']} duplicates)."
        )

    if not all_rows:
        print("No new entries downloaded.")

    write_metadata(out_dir, all_rows)
    print("Done.")

if __name__ == "__main__":
    args = parse_args()
    allowed = parse_allowed_tags(args.allow_tags)
    keywords = parse_keywords(args.cs_keywords)
    get_papers(
        date=args.date,
        allowed_tags=allowed,
        out_dir=args.out,
        sleep=args.sleep,
        include_cs_lg=args.include_cs_lg,
        cs_keywords=keywords if args.include_cs_lg else None,
        keyword_mode=args.keyword_mode,
    )
