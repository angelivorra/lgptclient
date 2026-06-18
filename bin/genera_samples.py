import os
import shutil

# Configure ffmpeg path before importing pydub
script_dir = os.path.dirname(os.path.abspath(__file__))
os.environ["PATH"] = script_dir + os.pathsep + os.environ.get("PATH", "")

from pydub import AudioSegment
from pydub.silence import detect_nonsilent

def trim_silence(audio: AudioSegment, silence_thresh: int = -50, min_silence_len: int = 500) -> AudioSegment:
    non_silent_ranges = detect_nonsilent(audio, min_silence_len=min_silence_len, silence_thresh=silence_thresh)
    if non_silent_ranges:
        start_trim = non_silent_ranges[0][0]
        end_trim = non_silent_ranges[-1][1]
        return audio[start_trim:end_trim]
    return audio

def convert_audio_files(folder_origin: str, folder_destiny: str):
    # Initialize counters
    total_origin_size = 0
    total_destiny_size = 0
    processed_files = 0
    skipped_files = 0
    failed_files = 0

    # Create folder_destiny if it doesn't exist (resume-friendly: do NOT wipe it)
    os.makedirs(folder_destiny, exist_ok=True)
    
    # Walk through all files in folder_origin
    for root, dirs, files in os.walk(folder_origin):
        for file in files:
            # Skip macOS AppleDouble metadata files (._*), they are not valid audio
            if file.startswith('._'):
                continue
            # Check if the file is mp3 or wav
            if file.endswith('.mp3') or file.endswith('.wav'):
                file_path = os.path.join(root, file)

                # Compute the destination path up front so we can resume
                relative_path = os.path.relpath(file_path, folder_origin)
                dest_file_path = os.path.join(folder_destiny, relative_path)
                dest_file_path = dest_file_path.rsplit('.', 1)[0] + '.wav'

                # Skip if already processed (resume where we left off)
                if os.path.exists(dest_file_path):
                    skipped_files += 1
                    continue

                # Process the file; a single bad/corrupt file must not abort
                # the whole run, so catch any error, report it and continue.
                try:
                    # Get the origin file size
                    origin_size = os.path.getsize(file_path)

                    # Load the audio file
                    audio = AudioSegment.from_file(file_path)

                    # Trim silence
                    trimmed_audio = trim_silence(audio)

                    # Convert to mono and 16-bit
                    audio = trimmed_audio.set_channels(1).set_sample_width(2)

                    # Ensure the directory exists in folder_destiny
                    dest_folder = os.path.dirname(dest_file_path)
                    os.makedirs(dest_folder, exist_ok=True)

                    # Save the file as a .wav in the same relative structure.
                    # Write to a temp file first, then atomically rename, so an
                    # interrupted run never leaves a half-written .wav that the
                    # resume check would mistake for a finished file.
                    tmp_file_path = dest_file_path + '.tmp'
                    audio.export(tmp_file_path, format='wav')
                    os.replace(tmp_file_path, dest_file_path)

                    # Get the destination file size
                    destiny_size = os.path.getsize(dest_file_path)

                    total_origin_size += origin_size
                    total_destiny_size += destiny_size
                    processed_files += 1

                    # Print file size details
                    print(f"Processed: {file}")
                    print(f"Origin size: {origin_size / (1024 ** 2):.2f} MB, Destiny size: {destiny_size / (1024 ** 2):.2f} MB")
                except Exception as e:
                    failed_files += 1
                    print(f"!! ERROR procesando {file_path}: {e}")
                    # Clean up any leftover temp file from a failed export
                    tmp_file_path = dest_file_path + '.tmp'
                    if os.path.exists(tmp_file_path):
                        try:
                            os.remove(tmp_file_path)
                        except OSError:
                            pass
                    continue

    # Print final statistics
    print("\nProcessing complete!")
    print(f"Total files processed: {processed_files}")
    print(f"Total files skipped (already done): {skipped_files}")
    print(f"Total files failed: {failed_files}")
    print(f"Total origin size: {total_origin_size / (1024 ** 2):.2f} MB")
    print(f"Total destiny size: {total_destiny_size / (1024 ** 2):.2f} MB")

# Get paths relative to script directory
script_dir = os.path.dirname(os.path.abspath(__file__))
origen_path = os.path.join(os.path.dirname(script_dir), 'samples', 'origen')
destino_path = os.path.join(os.path.dirname(script_dir), 'samples', 'destino')

convert_audio_files(origen_path, destino_path)
