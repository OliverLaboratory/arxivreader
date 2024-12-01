import os
import argparse
import re
from datetime import datetime
from pathlib import Path
import tempfile

from liturgy.get_liturgy import fetch_liturgy
from liturgy.tts import get_audio
from liturgy.build_track import build_track

chunk_size = 2


def cline():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Date in dd.mm.yyyy format, or 'today'", default="today")
    return parser.parse_args()


def split_prayer(prayer):
    text = " ".join(prayer)
    sentences = re.split(r"(?<=[.!?]) +", text)
    return sentences


def build_episode(args):

    Path("texts").mkdir(parents=True, exist_ok=True)

    for mode in ["lauds", "vespers"]:
        prayers = fetch_liturgy(query_date=args.date, hour=mode)
        songs = list(os.listdir("music"))
        music = f"music/{songs[hash(args.date) % len(songs)]}"
        all_text = ""
        fg_paths = []
        with tempfile.TemporaryDirectory() as tmpdir:
            for i, prayer in enumerate(prayers):
                prayer_paths = []
                prayer = split_prayer(prayer)
                for i in range(0, len(prayer), chunk_size):
                    text = " ".join(prayer[i : i + chunk_size])
                    all_text += text + "\n"
                    audio_path = get_audio(text, recompute=True, save_dir=tmpdir)
                    prayer_paths.append(audio_path)
                all_text += "\n" + "_" * 12 + "\n\n"
                fg_paths.append(prayer_paths)
            date_clean = args.date.replace(".", "")
            build_track(fg_paths, music, f"episodes/{date_clean}{mode}.mp3", overwrite=True)

        with open(f"texts/{date_clean}{mode}.txt", "w") as txt:
            txt.write(all_text)


if __name__ == "__main__":
    build_episode(cline())
