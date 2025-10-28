#!/usr/bin/env python3
"""
Generate and upload an Apple Podcasts–compliant RSS feed to DigitalOcean Spaces.

Fixes included vs. your last version:
- No `feedgen.ext.atom` import (avoids ModuleNotFoundError).
- Adds <atom:link rel="self"> manually via ElementTree (optional but nice).
- Correct Spaces endpoint vs. public URL; consistent key prefix (mlcb/…).
- Stable GUID (the enclosure URL), RFC-2822 pubDate, itunes:duration, episodic type.
- Correct MIME types on upload.

Requires:
  pip install boto3 feedgen pydub
  # and system ffmpeg/ffprobe for pydub.mediainfo (apt-get install -y ffmpeg)

Environment/files:
  SPACES_ACCESS.txt  -> first line is Spaces access key
  SPACES_SECRET.txt  -> first line is Spaces secret
  episodes/YYYY-MM-DD.mp3
  titles/YYYY-MM-DD.txt           (optional, first line used as title suffix)
  texts/YYYY-MM-DD.txt            (optional, appended to description)
  mlcb.jpg                        (square 1400–3000px RGB)
"""

import os
from pathlib import Path
from datetime import datetime, timezone
import boto3
from feedgen.feed import FeedGenerator
from pydub.utils import mediainfo
from xml.etree import ElementTree as ET

# ---------- DigitalOcean Spaces config ----------
SPACE_NAME = "mlcb"
REGION = "nyc3"

# S3 API endpoint (boto3) and public base URL for objects
SPACE_ENDPOINT = f"https://{REGION}.digitaloceanspaces.com"
PUBLIC_BASE = f"https://{SPACE_NAME}.{REGION}.digitaloceanspaces.com"

# Objects live under this prefix/folder inside the Space
KEY_PREFIX = "mlcb"

# Final public feed URL (what you submit to directories)
FEED_URL = f"{PUBLIC_BASE}/{KEY_PREFIX}/mlcb.xml"

# Credentials from local files
ACCESS_KEY = Path("SPACES_ACCESS.txt").read_text().splitlines()[0].strip()
SECRET_KEY = Path("SPACES_SECRET.txt").read_text().splitlines()[0].strip()

# Boto3 client
session = boto3.session.Session()
client = session.client(
    "s3",
    region_name=REGION,
    endpoint_url=SPACE_ENDPOINT,
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
)

# ---------- Helpers ----------

def get_mp3_duration_hhmmss(file_path: str) -> str:
    """Return HH:MM:SS duration using ffprobe via pydub.mediainfo."""
    info = mediainfo(file_path)  # needs ffprobe in PATH
    duration_seconds = float(info["duration"])
    h = int(duration_seconds // 3600)
    m = int((duration_seconds % 3600) // 60)
    s = int(duration_seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def upload_public(key: str, local_path: str, content_type: str) -> str:
    """Upload file to Spaces with public-read ACL and return public URL."""
    client.upload_file(
        local_path,
        SPACE_NAME,
        key,
        ExtraArgs={"ContentType": content_type, "ACL": "public-read"},
    )
    return f"{PUBLIC_BASE}/{key}"

def upload_episode(local_path: str) -> str:
    """Upload episode to mlcb/episodes/<filename> and return public URL."""
    file_name = os.path.basename(local_path)
    key = f"{KEY_PREFIX}/episodes/{file_name}"
    return upload_public(key, local_path, "audio/mpeg")

def pubdate_from_filename(date_str: str) -> datetime:
    """YYYY-MM-DD -> datetime at 00:00:00 UTC (Apple wants RFC-2822; feedgen formats it)."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.replace(tzinfo=timezone.utc)

# ---------- Feed generation ----------

def update_feed():
    fg = FeedGenerator()
    fg.load_extension("podcast")  # adds itunes namespace

    # Channel metadata (meets Apple requirements)
    fg.id(FEED_URL)
    fg.title("Machine Learning in Computational Biology: Daily Digest")
    fg.link(href=FEED_URL, rel="self")  # RSS self-link
    fg.link(href=f"{PUBLIC_BASE}/{KEY_PREFIX}", rel="alternate")
    fg.language("en")
    fg.description(
        "Daily summaries of preprints in machine learning and computational biology.\n"
        "Source code: https://github.com/OliverLaboratory/arxivreader"
    )

    # Apple Podcasts tags
    fg.podcast.itunes_author("Carlos Oliver")
    fg.author({"name": "Carlos Oliver", "email": "carlos.oliver@vanderbilt.edu"})
    fg.podcast.itunes_owner("Carlos Oliver", "carlos.oliver@vanderbilt.edu")
    fg.podcast.itunes_category("Science", "Life Sciences")
    fg.podcast.itunes_explicit("no")
    fg.podcast.itunes_type("episodic")
    fg.podcast.itunes_image(f"{PUBLIC_BASE}/{KEY_PREFIX}/mlcb.jpg")

    # Optional RSS image
    fg.image(
        f"{PUBLIC_BASE}/{KEY_PREFIX}/mlcb.jpg",
        title="Podcast Image",
        link=f"{PUBLIC_BASE}/{KEY_PREFIX}/mlcb.jpg",
    )

    # Collect local episodes
    episodes_dir = Path("episodes")
    if not episodes_dir.exists():
        print("No episodes/ directory found.")
        return

    notes_msg = "Source code: https://github.com/OliverLaboratory/arxivreader"

    # Sorted so feed is stable (YYYY-MM-DD lexicographic works)
    for mp3 in sorted(episodes_dir.glob("*.mp3")):
        date_str = mp3.stem  # YYYY-MM-DD
        try:
            pub_dt = pubdate_from_filename(date_str)
        except ValueError:
            print(f"Skipping {mp3.name}: filename must be YYYY-MM-DD.mp3")
            continue

        # Upload episode and gather metadata
        audio_url = upload_episode(str(mp3))
        size_bytes = os.path.getsize(mp3)
        duration = get_mp3_duration_hhmmss(str(mp3))

        title_suffix = Path(f"titles/{date_str}.txt").read_text(encoding="utf-8").splitlines()[0].strip() if Path(f"titles/{date_str}.txt").exists() else "Daily Digest"
        notes = Path(f"texts/{date_str}.txt").read_text(encoding="utf-8") if Path(f"texts/{date_str}.txt").exists() else ""

        ep_title = f"{date_str.split('-')[2]}.{date_str.split('-')[1]}.{date_str.split('-')[0]}: {title_suffix}"
        description = f"{notes}\n\n{notes_msg}"

        # Add feed entry
        fe = fg.add_entry()
        fe.title(ep_title)
        fe.description(description)
        fe.pubDate(pub_dt)  # feedgen renders RFC-2822
        fe.enclosure(audio_url, size_bytes, "audio/mpeg")
        fe.guid(audio_url, permalink=True)               # stable ID = enclosure URL
        fe.podcast.itunes_explicit("no")
        fe.podcast.itunes_episode_type("full")
        fe.podcast.itunes_duration(duration)             # HH:MM:SS

    # Write RSS to bytes, inject atom:link rel="self", then save/upload
    rss_bytes = fg.rss_str(pretty=True)

    ATOM_NS = "http://www.w3.org/2005/Atom"
    ET.register_namespace("atom", ATOM_NS)
    root = ET.fromstring(rss_bytes)
    channel = root.find("channel")
    if channel is not None:
        # Add atom:link rel="self" (optional but helps validators)
        ET.SubElement(
            channel,
            f"{{{ATOM_NS}}}link",
            {"href": FEED_URL, "rel": "self", "type": "application/rss+xml"},
        )

    local_feed = "mlcb.xml"
    ET.ElementTree(root).write(local_feed, encoding="utf-8", xml_declaration=True)

    # Upload feed to mlcb/mlcb.xml
    upload_public(f"{KEY_PREFIX}/{Path(local_feed).name}", local_feed, "application/rss+xml; charset=utf-8")
    print(f"Podcast feed generated and uploaded: {FEED_URL}")

def main():
    update_feed()

if __name__ == "__main__":
    main()
