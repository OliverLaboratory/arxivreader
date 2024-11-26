import requests
import base64
import json
import os

API_BASE_URL = "https://api.sws.speechify.com"
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


def get_audio(text):
    url = f"{API_BASE_URL}/v1/audio/speech"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    body = {"input": f"<speak>{text}</speak>", "emotion": "calm", "voice_id": VOICE_ID, "audio_format": "mp3"}

    response = requests.post(url, headers=headers, data=json.dumps(body))

    if not response.ok:
        raise Exception(f"{response.status_code} {response.reason}\n{response.text}")

    response_data = response.json()
    decoded_audio_data = base64.b64decode(response_data["audio_data"])
    return decoded_audio_data


def main():
    audio = get_audio("Hello, world!")
    with open("speech.mp3", "wb") as file:
        file.write(audio)


if __name__ == "__main__":
    main()
