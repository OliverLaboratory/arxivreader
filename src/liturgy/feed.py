import boto3
from pathlib import Path
from feedgen.feed import FeedGenerator
import os
from pydub.utils import mediainfo
import wave
from datetime import timedelta
from datetime import datetime

# DigitalOcean Spaces credentials
SPACE_NAME = "liturgy"
REGION = "nyc3"
ENDPOINT_URL = f"https://{SPACE_NAME}.{REGION}.digitaloceanspaces.com"
ACCESS_KEY = open("SPACES_ACCESS.txt").readline().strip()
SECRET_KEY = open("SPACES_SECRET.txt").readline().strip()

# Podcast details
FEED_URL = "https://{SPACE_NAME}.{REGION}.digitaloceanspaces.com/liturgy.xml"
LOCAL_FEED_FILE = "liturgy.xml"
BUCKET_BASE_URL = f"https://{SPACE_NAME}.{REGION}.digitaloceanspaces.com"

# Initialize Spaces client
session = boto3.session.Session()
client = session.client(
    "s3",
    region_name=REGION,
    endpoint_url=ENDPOINT_URL,
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
)


def get_mp3_duration(file_path):
    # Get media info
    info = mediainfo(file_path)

    # Duration in seconds
    duration_seconds = float(info["duration"])

    # Convert to hh:mm:ss format
    hours = int(duration_seconds // 3600)
    minutes = int((duration_seconds % 3600) // 60)
    seconds = int(duration_seconds % 60)

    return f"{hours:02}:{minutes:02}:{seconds:02}"


def get_wav_duration_hms(file_path):
    with wave.open(file_path, "r") as wav_file:
        frames = wav_file.getnframes()
        rate = wav_file.getframerate()
        duration_seconds = int(frames / float(rate))
        duration_hms = str(timedelta(seconds=duration_seconds))
        return duration_hms


def upload_episode(file_path):
    """Upload an episode to DigitalOcean Space."""
    file_name = os.path.basename(file_path)
    client.upload_file(file_path, SPACE_NAME, file_name, ExtraArgs={"ContentType": "audio/mpeg", "ACL": "public-read"})
    return f"{BUCKET_BASE_URL}/{file_name}"


def convert_date(date_str):
    # Parse the date in MM.DD.YYYY format
    date_obj = datetime.strptime(date_str, "%d.%m.%Y")
    # Format it into Mon, 01 Jan 2024 00:00:00 GMT
    return date_obj.strftime("%a, %d %b %Y 00:00:00 GMT")


def update_feed():
    """Update the podcast feed with a new episode."""

    # Initialize the feed generator
    fg = FeedGenerator()
    fg.load_extension("podcast")
    fg.id(FEED_URL)
    fg.title("Liturgy of the Hours")
    fg.link(href=FEED_URL, rel="self")
    fg.description("Daily reading from Liturgy of the Hours.")
    fg.language("en")

    # Include the email in the author field
    fg.author({"name": "Carlos Oliver", "email": "c.gqq9t@passmail.net"})  # Add your name and email
    fg.podcast.itunes_category("Religion")
    fg.podcast.itunes_explicit("no")
    fg.podcast.itunes_owner("Carlos Oliver", "c.gqq9t@passmail.net")
    fg.podcast.itunes_author("Carlos Oliver")

    # Optional: Add podcast image (Spotify supports square images)
    fg.image(
        f"https://liturgy.nyc3.digitaloceanspaces.com/liturgy/cover.png",
        title="Podcast Image",
        link="https://liturgy.nyc3.digitaloceanspaces.com/liturgy/cover.png",
    )

    # Add episodes to the podcast
    episodes = []
    for episode in os.listdir("episodes"):
        print(episode)
        upload_episode(os.path.join("episodes", episode))
        date, mode = Path(episode).stem.split("_")
        episodes.append(
            {
                "title": f"{date}: {mode}",
                # 'link': f"{BUCKET_BASE_URL}/{episode}",
                "description": f"{date}",
                "pub_date": convert_date(date),
                "audio_url": f"{BUCKET_BASE_URL}/{episode}",
                "duration": get_mp3_duration(f"episodes/{episode}"),  # Duration in format hh:mm:ss
                "explicit": "no",  # Mark as explicit or not
            }
        )

    # Loop over each episode and add it to the feed
    for episode in episodes:
        fe = fg.add_entry()
        fe.title(episode["title"])
        fe.author(name="Carlos Oliver", email="c.gqq9t@passmail.net")
        # fe.link(href=episode['link'])
        fe.description(episode["description"])
        fe.pubDate(episode["pub_date"])
        fe.enclosure(episode["audio_url"], 0, "audio/mpeg")  # Enclosure for audio file (MP3)
        fe.guid(episode["description"], permalink=False)
        # fe.itunes_duration(episode["duration"])  # Optional: Add iTunes duration tag
        # fe.itunes_explicit(episode["explicit"])  # Explicit content flag for Spotify

    # Generate and save the podcast RSS feed to a file
    fg.rss_file("liturgy.xml")

    print("Podcast feed for Spotify generated: liturgy.xml")

    fg.rss_file(LOCAL_FEED_FILE)
    client.upload_file(
        LOCAL_FEED_FILE,
        SPACE_NAME,
        os.path.basename(LOCAL_FEED_FILE),
        ExtraArgs={"ContentType": "application/rss+xml", "ACL": "public-read"},
    )


def main():
    # Upload new episode
    # Update feed
    update_feed()
    print("Podcast feed updated!")


if __name__ == "__main__":
    main()
