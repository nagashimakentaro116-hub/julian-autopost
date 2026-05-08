"""
Instagram Reels One-Shot Poster
VIDEO_URL 環境変数で指定した動画を Instagram Reels として投稿する
"""

import requests
import time
import os
import tempfile
import anthropic

INSTAGRAM_ACCESS_TOKEN = os.environ["INSTAGRAM_ACCESS_TOKEN"]
IG_USER_ID = "26471868175804350"
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
VIDEO_URL = os.environ["VIDEO_URL"]
API_BASE = "https://graph.instagram.com/v21.0"

CAPTION_FOOTER = (
    "\n\n📍 New York, NY\n"
    "#newyork #nyc #aiavatar #passiveincome #aibusiness #digitalproducts "
    "#sidehustle #financialfreedom #entrepreneurlife #makemoneyonline"
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
            "content": "Write ONE short Instagram Reels caption for a video of a man walking through a city. Calm, powerful, declarative tone. 2-4 lines max. End with 'Link in bio.' Return only the caption text."
        }]
    )
    return message.content[0].text.strip() + CAPTION_FOOTER


def download_video(url):
    print(f"Downloading video from: {url}")
    resp = requests.get(url, stream=True, timeout=120, allow_redirects=True)
    resp.raise_for_status()
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    for chunk in resp.iter_content(chunk_size=8192):
        tmp.write(chunk)
    tmp.flush()
    print(f"Downloaded to: {tmp.name}")
    return tmp.name


def _upload_to_0x0(path):
    with open(path, "rb") as f:
        resp = requests.post("https://0x0.st", files={"file": f}, timeout=180)
    resp.raise_for_status()
    url = resp.text.strip()
    if not url.startswith("http"):
        raise Exception(f"0x0.st upload failed: {url}")
    return url


def _upload_to_litterbox(path):
    with open(path, "rb") as f:
        resp = requests.post(
            "https://litterbox.catbox.moe/resources/internals/api.php",
            data={"reqtype": "fileupload", "time": "72h"},
            files={"fileToUpload": f},
            timeout=180,
        )
    resp.raise_for_status()
    url = resp.text.strip()
    if not url.startswith("http"):
        raise Exception(f"litterbox upload failed: {url}")
    return url


def upload_to_public_url(path):
    for attempt, fn in enumerate([_upload_to_0x0, _upload_to_litterbox], 1):
        try:
            print(f"  Upload attempt {attempt}: {fn.__name__}")
            return fn(path)
        except Exception as e:
            print(f"  Attempt {attempt} failed: {e}")
    raise Exception("All upload attempts failed")


def create_media_container(video_url, caption):
    resp = requests.post(
        f"{API_BASE}/{IG_USER_ID}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true",
            "access_token": INSTAGRAM_ACCESS_TOKEN,
        }
    )
    data = resp.json()
    if "id" not in data:
        raise Exception(f"Container creation failed: {data}")
    return data["id"]


def wait_for_container(container_id, max_wait=300):
    for _ in range(max_wait // 10):
        resp = requests.get(
            f"{API_BASE}/{container_id}",
            params={"fields": "status_code", "access_token": INSTAGRAM_ACCESS_TOKEN}
        )
        status = resp.json().get("status_code", "")
        print(f"  Container status: {status}")
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise Exception("Container processing failed")
        time.sleep(10)
    raise Exception("Timeout waiting for container")


def publish_container(container_id):
    resp = requests.post(
        f"{API_BASE}/{IG_USER_ID}/media_publish",
        data={
            "creation_id": container_id,
            "access_token": INSTAGRAM_ACCESS_TOKEN,
        }
    )
    data = resp.json()
    if "id" not in data:
        raise Exception(f"Publish failed: {data}")
    return data["id"]


def send_email_notification(post_id, caption):
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        return
    html = f"""
    <h2>Instagram Reels 投稿完了</h2>
    <p><b>投稿ID:</b> {post_id}</p>
    <p><b>アカウント:</b> <a href="https://www.instagram.com/thejulianmethod/">@thejulianmethod</a></p>
    <hr>
    <p><b>キャプション:</b></p>
    <pre style="white-space:pre-wrap;font-family:inherit">{caption}</pre>
    """
    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": "Julian Bot <onboarding@resend.dev>",
                "to": "nagashimakentaro116@gmail.com",
                "subject": f"[Julian IG] 投稿完了 ID:{post_id}",
                "html": html,
            },
            timeout=30,
        )
        print(f"Email sent: {resp.status_code}")
    except Exception as e:
        print(f"Email exception: {e}")


def main():
    caption = generate_caption()
    print(f"Caption:\n{caption}\n")

    local_path = download_video(VIDEO_URL)

    print("Uploading to public host...")
    public_url = upload_to_public_url(local_path)
    print(f"Public URL: {public_url}")

    print("Creating media container...")
    container_id = create_media_container(public_url, caption)
    print(f"Container ID: {container_id}")

    print("Waiting for processing...")
    wait_for_container(container_id)

    print("Publishing...")
    post_id = publish_container(container_id)
    print(f"SUCCESS: Published post ID {post_id}")

    send_email_notification(post_id, caption)
    print("Done.")


if __name__ == "__main__":
    main()
