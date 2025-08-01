import os
from data_pipelines import config
from whisperx.diarize import DiarizationPipeline
from pyannote.audio import Model
from sklearn.metrics.pairwise import cosine_similarity
import torch
import numpy as np
import whisperx

def load_speaker_profiles(profiles_dir=str(config.SPEAKER_PROFILES_DIR)):
    """Loads speaker profiles from the specified directory."""
    if not os.path.isdir(profiles_dir):
        return {}
    
    profiles = {}
    for filename in os.listdir(profiles_dir):
        if filename.endswith(".pt"):
            speaker_name = os.path.splitext(filename)[0]
            profile_path = os.path.join(profiles_dir, filename)
            embedding = torch.load(profile_path)
            profiles[speaker_name] = embedding
    print(f"Loaded {len(profiles)} speaker profile(s).")
    return profiles

def recognize_speakers(diarize_result, audio, speaker_profiles, hf_token, threshold=0.7):
    """Recognizes speakers based on enrolled profiles."""
    if not speaker_profiles:
        return {}

    embedding_model = Model.from_pretrained("pyannote/embedding", use_auth_token=hf_token)
    speaker_mapping = {}
    
    for _, segment in diarize_result.iterrows():
        speaker_label = segment['speaker']
        if speaker_label in speaker_mapping:
            continue

        # Extract embedding for the speaker in the new audio
        start_frame = int(segment['start'] * 16000)
        end_frame = int(segment['end'] * 16000)
        segment_waveform = torch.tensor(audio[start_frame:end_frame]).unsqueeze(0)
        
        with torch.no_grad():
            new_embedding = embedding_model(segment_waveform)

        # Compare with enrolled profiles
        max_similarity = 0
        best_match = None
        for name, enrolled_embedding in speaker_profiles.items():
            similarity = cosine_similarity(new_embedding, enrolled_embedding)[0][0]
            if similarity > max_similarity:
                max_similarity = similarity
                best_match = name
        
        if max_similarity > threshold:
            speaker_mapping[speaker_label] = best_match
        else:
            # If no good match is found, assign a generic label
            # This logic needs to be improved to handle multiple unknown speakers
            speaker_mapping[speaker_label] = "CUSTOMER"

    return speaker_mapping

def get_speaker_timeline(audio_path: str, hf_token: str, transcript_result: dict, recognize: bool = False, recognition_threshold: float = 0.7):
    """
    Uses pyannote.audio to get a speaker timeline for the audio file.
    """
    if not hf_token:
        raise ValueError("Hugging Face token (hf_token) is required for diarization.")

    print("Aligning transcription for diarization...")
    audio = whisperx.load_audio(audio_path)
    model_a, metadata = whisperx.load_align_model(language_code=transcript_result["language"], device="cpu")
    aligned_result = whisperx.align(transcript_result["segments"], model_a, metadata, audio, device="cpu", return_char_alignments=False)

    print("Diarising speakers...")
    diarize_model = DiarizationPipeline(use_auth_token=hf_token, device="cpu")
    diarize_segments = diarize_model(audio)
    result = whisperx.assign_word_speakers(diarize_segments, aligned_result)

    if recognize:
        print("Recognizing speakers...")
        speaker_profiles = load_speaker_profiles()
        speaker_mapping = recognize_speakers(diarize_segments, audio, speaker_profiles, hf_token, recognition_threshold)
        
        # Update speaker labels in the result
        for segment in result["segments"]:
            if 'speaker' in segment:
                original_speaker = segment['speaker']
                segment['speaker'] = speaker_mapping.get(original_speaker, original_speaker)

    return result