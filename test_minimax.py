import os
import httpx
from openai import OpenAI

client = OpenAI(
    api_key="sk-cp-rOB2azclrj-YFiW_Zm2fuS48kSrQPqFChbA-fvdSTeRDE3nDafOJN_uSv4IcIHuXBgiel8n-SMBqYlrRB1MLSN8M2sVOZ2p6eA6PoXEvR0BPgQ-oYE_zVIY",
    base_url="https://api.minimax.chat/v1",
)

try:
    response = client.chat.completions.create(
        model="minimax-m2.7",
        messages=[{"role": "user", "content": "你好"}],
    )
    print(response.choices[0].message.content)
except Exception as e:
    print(f"Error: {e}")
