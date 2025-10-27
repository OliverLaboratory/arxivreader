import os
from pydub import AudioSegment
from pydub.effects import normalize
import numpy as np
import tempfile


def slow_down_audio(audio_segment, speed_factor):
    """
    Slow down the audio segment by changing its sample rate.

    :param audio_segment: The Pydub AudioSegment to slow down.
    :param speed_factor: The factor by which to slow down the audio.
                          For example, 0.5 will make the audio half as fast.
    :return: Slowed down audio segment.
    """
    # Change sample rate (slower audio)
    slowed_audio = audio_segment.set_frame_rate(int(audio_segment.frame_rate * speed_factor))

    return slowed_audio


def stitch_audio_segments_with_silence(segments, silence_duration=3000):
    combined = AudioSegment.empty()
    silence = AudioSegment.silent(duration=300)  # 3000 ms = 3 seconds of silence
    for i, audio in enumerate(segments):
        combined += audio
        # Add silence between tracks except after the last track
        if i < len(segments) - 1:
            combined += silence
    return combined


def _ms_to_hms(ms: int) -> str:
    """Format milliseconds as H:MM:SS.mmm (hours omitted if 0)."""
    s, ms_part = divmod(int(ms), 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"

def stitch_mp3_files_with_silence(mp3_files, silence_duration=3000,
                                  add_leading_silence=False):
    """
    Combine multiple MP3 files into one, with silence between them, and
    return the start timestamp of each clip within the combined audio.

    :param mp3_files: List[str] of MP3 file paths
    :param silence_duration: Duration of silence (ms) between clips.
                             Also used as an optional leading pad before the first clip.
    :param add_leading_silence: If True, prepend `silence_duration` ms before the first clip.
    :return: (combined: AudioSegment,
              timestamps_ms: List[int],   # start times (ms) of each clip
              timestamps_str: List[str])  # human-readable H:MM:SS.mmm
    """
    # Start with optional leading silence
    combined = (AudioSegment.silent(duration=silence_duration)
                if add_leading_silence else AudioSegment.empty())

    timestamps_ms = []
    cursor = len(combined)  # where the next clip will start (in ms)

    for i, mp3_file in enumerate(mp3_files):
        audio = AudioSegment.from_mp3(mp3_file)

        # Record the start time for this clip (relative to the final stitched audio)
        timestamps_ms.append(cursor)

        # Append the audio
        combined += audio
        cursor = len(combined)

        # Add inter-clip silence except after the last track
        if i < len(mp3_files) - 1:
            combined += AudioSegment.silent(duration=silence_duration)
            cursor = len(combined)

    timestamps_str = [_ms_to_hms(ms) for ms in timestamps_ms]
    return combined, timestamps_str


def add_background_music(main_audio, background_audio_path, foreground_volume=0, background_volume=-20):
    """
    Superimpose background music on the main audio with volume adjustment.

    :param main_audio: AudioSegment object of the main audio
    :param background_audio_path: Path to the background music MP3 file
    :param foreground_volume: Volume adjustment for the main audio (in dB)
    :param background_volume: Volume adjustment for the background music (in dB)
    :return: AudioSegment with background music added
    """
    background = AudioSegment.from_mp3(background_audio_path)

    # Adjust volumes
    main_audio = main_audio + foreground_volume
    main_audio += AudioSegment.silent(duration=5000)
    background = background + background_volume

    # Loop background music to match the length of the main audio
    if len(background) < len(main_audio):
        loop_count = len(main_audio) // len(background) + 1
        background = background * loop_count

    # effects
    # print(f"adding reverb")
    # main_audio = add_reverb(main_audio)
    # print(f"adding distort")
    # main_audio = add_distortion(main_audio, gain=1.4)
    # Trim background to match the exact length of the main audio
    background = background[: len(main_audio)]

    fade_duration = 5000  # 5 seconds (in milliseconds)
    background = background.fade_out(fade_duration)

    # Overlay background music on the main audio
    return main_audio.overlay(background)


def save_mp3(audio_segment, output_path):
    """
    Save an AudioSegment as an MP3 file.
    """
    audio_segment.export(output_path, format="mp3")


def build_track(mp3_files, output_path, overwrite=False):

    # Stitch the MP3 files with silence
    print("Stitching MP3 files with silence...")
    final_audio, timestamps = stitch_mp3_files_with_silence(mp3_files,
                                                    silence_duration=3000)


    # Save the final audio
    print(f"Saving output to {output_path}...")
    save_mp3(final_audio, output_path)
    print("Done!")
    return output_path, timestamps

