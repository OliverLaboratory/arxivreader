import os
from datetime import datetime

from liturgy.get_liturgy import fetch_liturgy
from liturgy.tts import get_audio
from liturgy.build_track import build_track

chunk_size = 4


def build_episode():
    today = datetime.now()
    date = today.strftime("%d.%m.%Y")

    for mode in ["lauds", "vespers"]:
        prayers = fetch_liturgy()
        music = "music/anthony.mp3"
        fg_paths = []
        for i, prayer in enumerate(prayers):
            prayer_paths = []
            for i in range(0, len(prayer), chunk_size):
                audio_path = get_audio(" ".join(prayer[i : i + chunk_size]))
                prayer_paths.append(audio_path)
            fg_paths.append(prayer_paths)
        build_track(fg_paths, music, f"episodes/{date}_{mode}.mp3", overwrite=True)


if __name__ == "__main__":
    build_episode()
