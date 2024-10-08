import os
import shutil
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
    
    # Remove folder_destiny if it exists
    if os.path.exists(folder_destiny):
        shutil.rmtree(folder_destiny)
    
    # Create folder_destiny again
    os.makedirs(folder_destiny)
    
    # Walk through all files in folder_origin
    for root, dirs, files in os.walk(folder_origin):
        for file in files:
            # Check if the file is mp3 or wav
            if file.endswith('.mp3') or file.endswith('.wav'):
                file_path = os.path.join(root, file)
                processed_files += 1
                
                # Get the origin file size
                origin_size = os.path.getsize(file_path)
                total_origin_size += origin_size
                
                # Load the audio file
                audio = AudioSegment.from_file(file_path)
                
                # Trim silence
                trimmed_audio = trim_silence(audio)

                # Convert to mono and 16-bit
                audio = trimmed_audio.set_channels(1).set_sample_width(2)

                # Get the relative path and create the same structure in folder_destiny
                relative_path = os.path.relpath(file_path, folder_origin)
                dest_file_path = os.path.join(folder_destiny, relative_path)
                
                # Ensure the directory exists in folder_destiny
                dest_folder = os.path.dirname(dest_file_path)
                os.makedirs(dest_folder, exist_ok=True)

                # Save the file as a .wav in the same relative structure
                dest_file_path = dest_file_path.rsplit('.', 1)[0] + '.wav'
                audio.export(dest_file_path, format='wav')

                # Get the destination file size
                destiny_size = os.path.getsize(dest_file_path)
                total_destiny_size += destiny_size

                # Print file size details
                print(f"Processed: {file}")
                print(f"Origin size: {origin_size / (1024 ** 2):.2f} MB, Destiny size: {destiny_size / (1024 ** 2):.2f} MB")

    # Print final statistics
    print("\nProcessing complete!")
    print(f"Total files processed: {processed_files}")
    print(f"Total origin size: {total_origin_size / (1024 ** 2):.2f} MB")
    print(f"Total destiny size: {total_destiny_size / (1024 ** 2):.2f} MB")



convert_audio_files('/home/angel/lgptclient/lgpt/samplelibsrc', '/home/angel/lgptclient/lgpt/samplelib')
