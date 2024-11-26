from liturgy.get_liturgy import fetch_liturgy
from liturgy.tts import get_audio, get_voices

if __name__ == "__main__":
    prayers = fetch_liturgy()
    for i, prayer in enumerate(prayers):
        audio = get_audio(" ".join(prayer))
        with open(f"prayer_{i}.mp3", "wb") as file:
            file.write(audio)
    pass
