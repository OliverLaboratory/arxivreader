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
    parser.add_argument("--debug", help="Compile short snippet", default=False, action="store_true")
    return parser.parse_args()


def split_prayer(prayer):
    text = " ".join(prayer)
    sentences = re.split(r"(?<=[.!?]) +", text)
    return sentences


def build_episode(args):

    if args.date == "today":
        query_date = datetime.now().strftime("%Y%m%d")
        # Extract day, month, year
        year = query_date[:4]  # First 4 characters
        month = query_date[4:6]  # Characters 5 and 6
        day = query_date[6:]  # Characters 7 and 8
    else:
        day = args.date[:2]
        month = args.date[2:4]
        year = args.date[4:]
        query_date = year + month + day

    Path("texts").mkdir(parents=True, exist_ok=True)

    modes = ["lauds", "vespers"] if not args.debug else ["lauds"]

    for mode in modes:
        if args.debug:
            prayers = [
                [
                    "Our Father who art in heaven.",
                    "Hallowed be thy name.",
                    "Thy kingdom come, thy will be done.",
                    "On earth as it is in heaven.",
                    "On earth as it is in heaven.",
                    "Give us this day our daily bread.",
                    "And forgive us our trespasses, as we forgive those who trespass against us."
                    "And lead us not into temptation; but deliver us from evil.",
                    "Amen.",
                ]
            ]
        else:
            prayers = fetch_liturgy(query_date=query_date, hour=mode)
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
            date_clean = day + month + year
            if args.debug:
                build_track(fg_paths, music, f"debug.mp3", overwrite=True)
            else:
                build_track(fg_paths, music, f"episodes/{date_clean}{mode}.mp3", overwrite=True)

        with open(f"texts/{date_clean}{mode}.txt", "w") as txt:
            txt.write(all_text)


if __name__ == "__main__":
    build_episode(cline())
