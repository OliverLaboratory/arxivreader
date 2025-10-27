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
    silence = AudioSegment.silent(duration=3000)  # 3000 ms = 3 seconds of silence
    for i, audio in enumerate(segments):
        combined += audio
        # Add silence between tracks except after the last track
        if i < len(segments) - 1:
            combined += silence
    return combined


def stitch_mp3_files_with_silence(mp3_files, silence_duration=3000):
    """
    Combine multiple MP3 files into one, with silence between them.

    :param mp3_files: List of MP3 file paths
    :param silence_duration: Duration of silence in milliseconds between MP3s
    :return: Combined AudioSegment with silence between tracks
    """
    combined = AudioSegment.empty()
    silence = AudioSegment.silent(duration=3000)  # 3000 ms = 3 seconds of silence
    combined += silence
    for i, mp3_file in enumerate(mp3_files):
        audio = AudioSegment.from_mp3(mp3_file)
        #audio = slow_down_audio(audio, 0.70)
        combined += audio
        # Add silence between tracks except after the last track
        if i < len(mp3_files) - 1:
            combined += silence
    return combined


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
    if not os.path.exists(output_path) or overwrite:

        # Stitch the MP3 files with silence
        print("Stitching MP3 files with silence...")
        final_audio = stitch_mp3_files_with_silence(mp3_files,
                                                    silence_duration=30000)


        # Save the final audio
        print(f"Saving output to {output_path}...")
        save_mp3(final_audio, output_path)
        print("Done!")
    else:
        print(f"{output_path} already exists. Skipping.")
