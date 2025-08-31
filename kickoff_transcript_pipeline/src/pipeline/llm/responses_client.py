import os
from typing import Dict, Any
from openai import OpenAI


def fuse_block_via_llm(aligned_payload: Dict[str, Any], prompt_md: str, model: str, temperature: float) -> Dict[str, str]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    client = OpenAI(api_key=api_key)

    system = (
        "You are a careful transcript fusion assistant. Use only provided inputs. "
        "If inputs are missing/invalid, answer with a JSON error: {\"error\":\"fail_closed\",\"reason\":\"...\"}."
    )

    user_content = (
        prompt_md
        + "\n\nAligned input (JSON):\n"
        + str(aligned_payload)
        + "\n\nReturn strict JSON with keys: master_block, qa_block, outline_hint."
    )

    completion = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
    )

    text = completion.choices[0].message.content or "{}"
    # Rely on downstream to parse/validate strict JSON
    return {"raw": text}
