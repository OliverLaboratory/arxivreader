import requests
import hashlib
import random
import base64
import json
import os
from pathlib import Path

import torch
import numpy as np
from pydub import AudioSegment
from bark import SAMPLE_RATE, generate_audio, preload_models
from scipy.io.wavfile import write as write_wav

AUDIO_DB = "prayers"
VOICE_ID = "v2/en_speaker_3"

# download and load all models
# preload_models()

device = torch.device("cpu")
torch.set_num_threads(4)
local_file = "model.pt"

if not os.path.isfile(local_file):
    torch.hub.download_url_to_file("https://models.silero.ai/models/tts/en/v3_en.pt", local_file)

model = torch.package.PackageImporter(local_file).load_pickle("tts_models", "model")
model.to(device)
good_speakers = [4, 10]
speaker = f"en_{random.choice(good_speakers)}"
print(f"SPEAKER: {speaker}")


sample_rate = 44100  # Hz


def numpy_to_mp3(array, sample_rate, output_file):
    """
    Converts a NumPy array into an MP3 file.

    :param array: NumPy array representing audio data (float32 or int16).
    :param sample_rate: Sampling rate of the audio data (e.g., 44100 Hz).
    :param output_file: Output file path for the MP3.
    """
    # Normalize the array if it's in float format
    if array.dtype == np.float32:
        array = (array * 32767).astype(np.int16)  # Scale to int16 range

    # Convert NumPy array to raw audio bytes
    audio_bytes = array.tobytes()

    # Create an AudioSegment from raw audio data
    audio = AudioSegment(
        data=audio_bytes,
        sample_width=array.dtype.itemsize,  # 2 for int16
        frame_rate=sample_rate,
        channels=1,  # Mono audio
    )

    # Export to MP3
    audio.export(output_file, format="mp3")
    print(f"Saved to {output_file}")


def get_audio(text, engine="silero", recompute=False, save_dir="prayers"):
    hash_object = hashlib.md5(text.encode())  # MD5 hash
    hash_hex = hash_object.hexdigest()
    audio_path = Path(save_dir) / f"{hash_hex}.mp3"
    print(f"computing: {text} ")
    if not os.path.exists(audio_path) or recompute:
        if engine == "bark":
            audio_array = generate_audio(text, history_prompt=VOICE_ID)
        if engine == "silero":
            audio_array = model.apply_tts(text=text, speaker=speaker, sample_rate=SAMPLE_RATE).numpy()
        numpy_to_mp3(audio_array, SAMPLE_RATE, audio_path)
    print(f"wrote {text} audio to: ", audio_path)
    return audio_path


if __name__ == "__main__":
    get_audio("Our Father, who art in heaven. Hallowed be thy name. Thy kingdom come, thy will be done.")
    pass
