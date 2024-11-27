from datetime import datetime

from liturgy.get_liturgy import fetch_liturgy
from liturgy.tts import get_audio, get_voices
from liturgy.build_track import build_track


def build_episode():
    today = datetime.now()
    date = today.strftime("%d.%m.%Y")

    for mode in ["lauds", "vespers"]:
        prayers = fetch_liturgy()
        music = "music/anthony.mp3"
        fg_paths = []
        for i, prayer in enumerate(prayers):
            audio_path = get_audio(" ".join(prayer))
            fg_paths.append(audio_path)
        build_track(fg_paths, music, f"episodes/{date}_{mode}.mp3")


if __name__ == "__main__":
    build_episode()
