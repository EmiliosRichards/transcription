import os
import requests

def transcribe(audio_path: str) -> str:
    """
    Transcribes an audio file using the Mistral API's chat completions endpoint.
    """
    if "MISTRAL_API_KEY" not in os.environ:
        raise ValueError("MISTRAL_API_KEY environment variable not found.")
        
    api_key = os.environ["MISTRAL_API_KEY"]

    # Step 1: Upload the audio file
    upload_url = "https://api.mistral.ai/v1/files"
    headers = {"Authorization": f"Bearer {api_key}"}
    with open(audio_path, "rb") as f:
        files = {"file": (os.path.basename(audio_path), f)}
        upload_response = requests.post(upload_url, headers=headers, files=files, data={"purpose": "audio"})
    upload_response.raise_for_status()
    file_id = upload_response.json()["id"]

    # Step 2: Get a signed URL for the uploaded file
    signed_url_url = f"https://api.mistral.ai/v1/files/{file_id}/url?expiry=24"
    signed_url_response = requests.get(signed_url_url, headers=headers)
    signed_url_response.raise_for_status()
    signed_url = signed_url_response.json()["url"]

    # Step 3: Send the audio for inference
    chat_url = "https://api.mistral.ai/v1/chat/completions"
    chat_headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    chat_data = {
        "model": "voxtral-small-latest",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": signed_url, "format": "mp3"},
                    },
                    {"type": "text", "text": "Transcribe this audio file."},
                ],
            }
        ],
    }
    chat_response = requests.post(chat_url, headers=chat_headers, json=chat_data)
    chat_response.raise_for_status()
    return chat_response.json()["choices"][0]["message"]["content"]