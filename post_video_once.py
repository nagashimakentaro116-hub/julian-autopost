import requests
import time
import os
import anthropic

THREADS_ACCESS_TOKEN = os.environ["THREADS_ACCESS_TOKEN"]
THREADS_USER_ID = os.environ["THREADS_USER_ID"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

VIDEO_URL = os.environ.get(
    "VIDEO_URL",
    "https://github.com/nagashimakentaro116-hub/julian-autopost/releases/download/v-video-20260503212506/15.mp4"
)

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
"""

def generate_caption():
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        system=BRAND_GUIDELINES,
        messages=[{
            "role": "user",
            "content": "Write ONE short Threads caption for a video of a man walking through a city. Calm, powerful, declarative tone. 2-4 lines max. End with 'Link in bio.' Return only the caption."
        }]
    )
    return message.content[0].text.strip()

def post_video():
    caption = generate_caption()
    print(f"Caption:\n{caption}\n")

    # Step 1: コンテナ作成
    url = f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads"
    res = requests.post(url, params={
        "media_type": "VIDEO",
        "video_url": VIDEO_URL,
        "text": caption,
        "access_token": THREADS_ACCESS_TOKEN
    })
    data = res.json()
    print(f"Container: {data}")

    if "id" not in data:
        raise Exception(f"Container error: {data}")

    container_id = data["id"]

    # Step 2: FINISHED待ち
    print("Waiting for video processing...")
    for _ in range(20):
        time.sleep(10)
        s = requests.get(
            f"https://graph.threads.net/v1.0/{container_id}",
            params={"fields": "status,error_message", "access_token": THREADS_ACCESS_TOKEN}
        ).json()
        print(f"  status: {s}")
        if s.get("status") == "FINISHED":
            break
        elif s.get("status") == "ERROR":
            raise Exception(f"Video error: {s}")

    # Step 3: 投稿
    pub = requests.post(
        f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads_publish",
        params={"creation_id": container_id, "access_token": THREADS_ACCESS_TOKEN}
    ).json()
    print(f"Published: {pub}")

    if "id" not in pub:
        raise Exception(f"Publish error: {pub}")

    post_id = pub["id"]

    # Step 4: 同じキャプションをコメントとして投稿
    time.sleep(5)
    comment_container = requests.post(
        f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads",
        params={
            "media_type": "TEXT",
            "text": caption,
            "reply_to_id": post_id,
            "access_token": THREADS_ACCESS_TOKEN
        }
    ).json()
    print(f"Comment container: {comment_container}")

    if "id" not in comment_container:
        raise Exception(f"Comment container error: {comment_container}")

    time.sleep(3)
    comment_pub = requests.post(
        f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads_publish",
        params={"creation_id": comment_container["id"], "access_token": THREADS_ACCESS_TOKEN}
    ).json()
    print(f"Comment published: {comment_pub}")

if __name__ == "__main__":
    post_video()
    print("Done.")
