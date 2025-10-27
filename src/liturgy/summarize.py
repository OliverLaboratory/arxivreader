from __future__ import annotations
from pathlib import Path
from typing import Optional, Tuple

from openai import OpenAI


def make_summary(
    pdf_path: str | Path,
    out_path: str | Path = "summary.wav",
    *,
    text_model: str = "gpt-4.1",          # step 1: text summary
    tts_model: str = "gpt-4o-mini-tts",   # step 2: text-to-speech
    voice: str = "alloy",
    audio_format: str = "mp3",            # one of: mp3, opus, aac, flac, wav, pcm
) -> Tuple[Path, str]:
    """
    Two-step pipeline:
      1) Summarize the uploaded PDF into plain text with the Responses API.
      2) Convert that text into spoken audio and save it to `out_path`.

    Returns:
      (out_path: Path, summary_text: str)
    """
    client = OpenAI()

    pdf_path = Path(pdf_path)
    out_path = Path(out_path)

    # --- Step 0: upload PDF so the model can read it ---
    with pdf_path.open("rb") as f:
        uploaded = client.files.create(file=f, purpose="user_data")

    # --- Step 1: ask for a 700-word expert monologue summary (plain text only) ---
    prompt = (
        "summarize this pdf for a person who knows the field in about 500 words. "
        "don't give me any formatting or headers. just the text written as paragraphs, "
        "no bullet points. write as though it were a short spoken presentation about the paper. "
        "at the start state the title and the authors. no special characters."
    )

    resp = client.responses.create(
        model=text_model,
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_file", "file_id": uploaded.id},
            ],
        }],
    )

    summary_text = resp.output_text  # convenience property from the SDK
    if not summary_text or not summary_text.strip():
        raise RuntimeError("No summary text returned from the model.")

    # --- Step 2: synthesize the summary as speech and save to disk ---
    # Use streaming to write the audio efficiently.
    with client.audio.speech.with_streaming_response.create(
        model=tts_model,
        voice=voice,
        input=summary_text,
        response_format=audio_format,  # e.g., "wav" or "mp3"
    ) as speech:
        speech.stream_to_file(out_path)

    return out_path, summary_text


# Example usage:
# audio_path, summary = summarize_pdf_to_audio_two_step(
#     pdf_path="/path/to/paper.pdf",
#     out_path="paper_summary.wav",
#     text_model="gpt-4.1",
#     tts_model="gpt-4o-mini-tts",
#     voice="alloy",
#     audio_format="wav",
# )
# print(f"Saved audio to: {audio_path}")
