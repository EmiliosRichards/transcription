import os
import argparse
import torch
from pyannote.audio import Model
from pyannote.audio.pipelines import VoiceActivityDetection
from pyannote.core import Segment
import torchaudio

def enroll_speaker(audio_path, speaker_name, hf_token, profiles_dir="speaker_profiles"):
    """Extracts a speaker embedding from an audio file and saves it."""
    print(f"Enrolling speaker '{speaker_name}' from {audio_path}...")
    os.makedirs(profiles_dir, exist_ok=True)

    # Load pre-trained model for speaker embeddings
    embedding_model = Model.from_pretrained("pyannote/embedding", use_auth_token=hf_token)
    
    waveform, sample_rate = torchaudio.load(audio_path)
    
    # Ensure waveform is in the correct format (mono, correct sample rate)
    if waveform.shape[0] > 1:
        waveform = torch.mean(waveform, dim=0, keepdim=True)
    if sample_rate != embedding_model.hparams['sample_rate']:
        resampler = torchaudio.transforms.Resample(orig_freq=sample_rate, new_freq=embedding_model.hparams['sample_rate'])
        waveform = resampler(waveform)

    # Get embedding from the entire audio clip
    with torch.no_grad():
        embedding = embedding_model(waveform.unsqueeze(0))

    # Save the embedding
    profile_path = os.path.join(profiles_dir, f"{speaker_name}.pt")
    torch.save(embedding, profile_path)
    print(f"Speaker profile saved to {profile_path}")

def main():
    parser = argparse.ArgumentParser(description="Enroll a new speaker from an audio file.")
    parser.add_argument("--name", type=str, required=True, help="Name of the speaker.")
    parser.add_argument("--audio", type=str, required=True, help="Path to the audio file for enrollment.")
    parser.add_argument("--hf_token", type=str, default=None, help="Hugging Face token for speaker embedding model.")
    args = parser.parse_args()

    enroll_speaker(args.audio, args.name, args.hf_token)

if __name__ == "__main__":
    main()