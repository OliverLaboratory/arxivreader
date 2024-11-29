import os
from pydub import AudioSegment
from pydub.effects import normalize
import numpy as np
import tempfile
from scipy.signal import convolve
from pedalboard import Pedalboard, Reverb, Distortion, Delay, HighpassFilter, LowpassFilter, Chorus, Resample


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


def add_effects(audio):
    # Step 2: Convert AudioSegment to NumPy array
    samples = np.array(audio.get_array_of_samples())
    if audio.channels == 2:  # Handle stereo audio
        samples = samples.reshape((-1, 2)).T  # Transpose to (channels, samples)

    # Normalize samples to -1.0 to 1.0 (as expected by Pedalboard)
    samples = samples / (2 ** (audio.sample_width * 8 - 1))

    # Step 3: Define Pedalboard effects
    board = Pedalboard(
        [
            Resample(target_sample_rate=int(audio.frame_rate * 0.65)),
            Distortion(drive_db=6),  # Add a gritty, lo-fi distortion
            HighpassFilter(cutoff_frequency_hz=150),  # Remove low frequencies
            LowpassFilter(cutoff_frequency_hz=4000),  # Remove high frequencies
            Reverb(room_size=0.3, damping=0.5, wet_level=0.2),  # Add ethereal reverb
            Delay(delay_seconds=0.2, feedback=0.10, mix=0.05),  # Add echo for atmosphere
            Chorus(rate_hz=0.2, depth=0.1, mix=0.05),  # Subtle pitch flutter to simulate tape wobble
        ]
    )

    # Apply the effects
    processed_samples = board(samples, audio.frame_rate)

    # Step 4: Denormalize processed samples back to integer format
    processed_samples = (processed_samples * (2 ** (audio.sample_width * 8 - 1))).astype(np.int16)

    # Step 5: Convert processed samples back to Pydub AudioSegment
    processed_audio = AudioSegment(
        processed_samples.tobytes(),
        frame_rate=audio.frame_rate,
        sample_width=audio.sample_width,
        channels=audio.channels,
    )
    return processed_audio


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
        audio = slow_down_audio(audio, 0.75)
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

    # Overlay background music on the main audio
    return main_audio.overlay(background)


def save_mp3(audio_segment, output_path):
    """
    Save an AudioSegment as an MP3 file.
    """
    audio_segment.export(output_path, format="mp3")


def build_track(fg_files, bkg_file, output_path, overwrite=False):
    if not os.path.exists(output_path) or overwrite:
        # List of MP3 files to stitch together
        mp3_files = fg_files  # Replace with your file paths

        # Path to the background music MP3 file
        background_music_path = bkg_file

        # Silence duration between tracks (in milliseconds)
        silence_duration = 3000  # 3 seconds

        # Volume adjustments (in dB)
        foreground_volume = -10  # Adjust the main audio volume (0 = no change)
        background_volume = -10  # Adjust the background music volume (negative reduces volume)

        # Stitch the MP3 files with silence
        print("Stitching MP3 files with silence...")
        prayers = []
        for prayer in fg_files:
            combined_audio = stitch_mp3_files_with_silence(prayer, 0)
            prayers.append(combined_audio)

        final_audio = stitch_audio_segments_with_silence(prayers)
        final_audio = add_effects(final_audio)
        # Add background music
        print("Adding background music...")
        final_audio = add_background_music(final_audio, background_music_path, foreground_volume, background_volume)

        # Save the final audio
        print(f"Saving output to {output_path}...")
        save_mp3(final_audio, output_path)
        print("Done!")
    else:
        print(f"{output_path} already exists. Skipping.")
