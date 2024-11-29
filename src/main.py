import os
import re
from datetime import datetime
import tempfile

from liturgy.get_liturgy import fetch_liturgy
from liturgy.tts import get_audio
from liturgy.build_track import build_track

chunk_size = 2


def split_prayer(prayer):
    text = " ".join(prayer)
    sentences = re.split(r"(?<=[.!?]) +", text)
    return sentences


def build_episode():
    today = datetime.now()
    date = today.strftime("%d.%m.%Y")

    for mode in ["lauds", "vespers"]:
        prayers = fetch_liturgy()
        music = "music/anthony.mp3"
        fg_paths = []
        with tempfile.TemporaryDirectory() as tmpdir:
            for i, prayer in enumerate(prayers):
                prayer_paths = []
                prayer = split_prayer(prayer)
                for i in range(0, len(prayer), chunk_size):
                    audio_path = get_audio(" ".join(prayer[i : i + chunk_size]), recompute=True, save_dir=tmpdir)
                    prayer_paths.append(audio_path)
                fg_paths.append(prayer_paths)
            date_clean = date.replace(".", "")
            build_track(fg_paths, music, f"episodes/{date_clean}{mode}.mp3", overwrite=True)


if __name__ == "__main__":
    build_episode()
