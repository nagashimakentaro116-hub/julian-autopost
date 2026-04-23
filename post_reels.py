"""
Instagram Reels Auto-Poster
~/Julian_Autopost/reels/ に入っているMP4を順番に投稿する
投稿済みはposted_reels.txt に記録してスキップ
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from datetime import datetime

# ─── 設定 ───────────────────────────────────────────
IG_USER_ID = "26471868175804350"
IG_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
REELS_DIR = Path(os.path.expanduser("~/Julian_Autopost/reels"))
POSTED_LOG = Path(os.path.expanduser("~/Julian_Autopost/posted_reels.txt"))
CAPTION_DEFAULT = (
    "The system runs. You don't have to.\n\n"
    "Julian | Operator Systems\n\n"
    "#AIbusiness #passiveincome #digitalproducts #onlinebusiness "
    "#aitools #solopreneur #makemoneyonline #workfromanywhere"
)
API_BASE = "https://graph.instagram.com/v21.0"
# ────────────────────────────────────────────────────


def load_posted():
    if POSTED_LOG.exists():
        return set(POSTED_LOG.read_text().splitlines())
    return set()


def mark_posted(filename):
    with open(POSTED_LOG, "a") as f:
        f.write(filename + "\n")


def get_next_reel():
    posted = load_posted()
    mp4_files = sorted(REELS_DIR.glob("*.mp4"))
    for f in mp4_files:
        if f.name not in posted:
            return f
    return None


def get_caption(reel_path):
    caption_file = reel_path.with_suffix(".txt")
    if caption_file.exists():
        return caption_file.read_text().strip()
    return CAPTION_DEFAULT


def upload_video_to_public_url(reel_path):
    """freeimage.host にアップロードして公開URLを取得"""
    url = "https://freeimage.host/api/1/upload"
    with open(reel_path, "rb") as f:
        resp = requests.post(url, data={"key": "6d207e02198a847aa98d0a2a901485a5"}, files={"source": f})
    data = resp.json()
    if data.get("status_code") == 200:
        return data["image"]["url"]
    raise Exception(f"Upload failed: {data}")


def create_media_container(video_url, caption):
    """Instagram Reels メディアコンテナを作成"""
    resp = requests.post(
        f"{API_BASE}/{IG_USER_ID}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true",
            "access_token": IG_TOKEN,
        }
    )
    data = resp.json()
    if "id" not in data:
        raise Exception(f"Container creation failed: {data}")
    return data["id"]


def wait_for_container(container_id, max_wait=300):
    """コンテナの処理完了を待つ"""
    for _ in range(max_wait // 10):
        resp = requests.get(
            f"{API_BASE}/{container_id}",
            params={"fields": "status_code", "access_token": IG_TOKEN}
        )
        status = resp.json().get("status_code", "")
        print(f"  Container status: {status}")
        if status == "FINISHED":
            return True
        if status == "ERROR":
            raise Exception("Container processing failed")
        time.sleep(10)
    raise Exception("Timeout waiting for container")


def publish_container(container_id):
    """コンテナを公開"""
    resp = requests.post(
        f"{API_BASE}/{IG_USER_ID}/media_publish",
        data={
            "creation_id": container_id,
            "access_token": IG_TOKEN,
        }
    )
    data = resp.json()
    if "id" not in data:
        raise Exception(f"Publish failed: {data}")
    return data["id"]


def main():
    if not IG_TOKEN:
        print("ERROR: INSTAGRAM_ACCESS_TOKEN not set")
        sys.exit(1)

    reel = get_next_reel()
    if not reel:
        print("No new reels to post.")
        return

    print(f"[{datetime.now().isoformat()}] Posting: {reel.name}")

    caption = get_caption(reel)
    print(f"Caption: {caption[:50]}...")

    print("Uploading video...")
    video_url = upload_video_to_public_url(reel)
    print(f"Video URL: {video_url}")

    print("Creating media container...")
    container_id = create_media_container(video_url, caption)
    print(f"Container ID: {container_id}")

    print("Waiting for processing...")
    wait_for_container(container_id)

    print("Publishing...")
    post_id = publish_container(container_id)
    print(f"SUCCESS: Published post ID {post_id}")

    mark_posted(reel.name)
    print(f"Marked as posted: {reel.name}")


if __name__ == "__main__":
    main()
