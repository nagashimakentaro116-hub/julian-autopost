import anthropic
import requests
import os
import json
import random

THREADS_ACCESS_TOKEN = os.environ["THREADS_ACCESS_TOKEN"]
THREADS_USER_ID = os.environ["THREADS_USER_ID"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

BRAND_GUIDELINES = """
You are a content writer for Julian, an AI operator character.

BRAND IDENTITY:
- Julian is an AI character (not human) who represents a digital product system
- Product: $147 PDF guide on building an AI operator brand on Instagram/Threads
- Target audience: English-speaking Americans interested in passive income, AI tools, digital products
- Tone: Quiet luxury, calm authority, no hype, no emojis, no exclamation marks
- Competitors use loud/hype tone — Julian is the OPPOSITE: silent, powerful, restrained

WRITING RULES:
- No emojis ever
- No exclamation marks
- Short sentences (1-3 words per line ideal)
- Always end with "Link in bio." on its own line
- Never use words: hustle, grind, guru, hack, secret, amazing, incredible
- Voice: calm, certain, slightly mysterious
- English must sound like a native American speaker

CONTENT TYPES (rotate):
1. Declarative: Bold single truth statement
2. Contrast: "Most people X. Operators Y."
3. List: "3 things operators never do: —"
4. Reveal: Exposing Julian as AI, humanizing the system
5. Proof: Reference to real numbers ($6,813, $147, built in one afternoon)
6. Philosophy: Short wisdom about ownership vs. effort
7. Question: Single open question to drive replies
"""

def generate_post():
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    content_types = ["declarative", "contrast", "list", "reveal", "proof", "philosophy", "question"]
    chosen_type = random.choice(content_types)

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        system=BRAND_GUIDELINES,
        messages=[{
            "role": "user",
            "content": f"Write ONE Threads post of type '{chosen_type}'. Return only the post text, nothing else."
        }]
    )

    return message.content[0].text.strip()

def post_to_threads(text):
    # コンテナ作成
    url = f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads"
    res = requests.post(url, params={
        "media_type": "TEXT",
        "text": text,
        "access_token": THREADS_ACCESS_TOKEN
    })
    data = res.json()

    if "id" not in data:
        raise Exception(f"Container error: {data}")

    container_id = data["id"]

    import time
    time.sleep(3)

    # 投稿
    pub_url = f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads_publish"
    res = requests.post(pub_url, params={
        "creation_id": container_id,
        "access_token": THREADS_ACCESS_TOKEN
    })
    pub_data = res.json()

    if "id" not in pub_data:
        raise Exception(f"Publish error: {pub_data}")

    return pub_data["id"]

def main():
    print("投稿文を生成中...")
    text = generate_post()
    print(f"生成完了:\n{text}\n")

    print("Threadsに投稿中...")
    thread_id = post_to_threads(text)
    print(f"投稿成功: thread_id={thread_id}")

if __name__ == "__main__":
    main()
