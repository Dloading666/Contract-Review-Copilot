import os

from openai import OpenAI

api_key = os.getenv("MINIMAX_API_KEY", "")
base_url = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.chat/v1")

if not api_key:
    raise RuntimeError("Please set MINIMAX_API_KEY before running this script")

client = OpenAI(api_key=api_key, base_url=base_url)

try:
    response = client.chat.completions.create(
        model="minimax-m2.7",
        messages=[{"role": "user", "content": "??"}],
    )
    print(response.choices[0].message.content)
except Exception as exc:
    print(f"Error: {exc}")
