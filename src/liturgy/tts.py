import requests
import hashlib
import base64
import json
import os
from pathlib import Path

API_BASE_URL = "https://api.sws.speechify.com"
AUDIO_DB = "prayers"
API_KEY = open("SECRET.txt", "r").readline().strip()
VOICE_ID = "rob"


def get_voices():
    url = f"{API_BASE_URL}/v1/voices"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()  # Raise an exception for HTTP errors
    return response.json()


def get_audio(text, recompute=False):
    hash_object = hashlib.md5(text.encode())  # MD5 hash
    hash_hex = hash_object.hexdigest()
    audio_path = f"{AUDIO_DB}/{hash_hex}.mp3"
    if not os.path.exists(audio_path) or recompute:
        print("Querying TTS...")
        url = f"{API_BASE_URL}/v1/audio/speech"
        headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
        body = {
            "input": f"<speak>{text}</speak>",
            "emotion": "calm",
            "voice_id": VOICE_ID,
            "audio_format": "mp3",
        }

        response = requests.post(url, headers=headers, data=json.dumps(body))

        if not response.ok:
            raise Exception(f"{response.status_code} {response.reason}\n{response.text}")

        response_data = response.json()
        decoded_audio_data = base64.b64decode(response_data["audio_data"])
        with open(audio_path, "wb") as file:
            file.write(decoded_audio_data)

    return audio_path


if __name__ == "__main__":
    main()
