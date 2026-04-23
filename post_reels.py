"""
Instagram Reels Auto-Poster
~/Julian_Autopost/reels/ に入っているMP4を順番に投稿する
投稿済みはposted_reels.txt に記録してスキップ

- captions.json からキャプションを順番に使う（個別 .txt があれば優先）
- reels/music/ のBGMをランダム選択してffmpegでマージ
"""

import os
import sys
import json
import time
import random
import tempfile
import subprocess
import shutil
import requests
from pathlib import Path
from datetime import datetime

# ─── 設定 ───────────────────────────────────────────
IG_USER_ID = "26471868175804350"
IG_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
BASE_DIR = Path(os.path.expanduser("~/Julian_Autopost"))
REELS_DIR = BASE_DIR / "reels"
MUSIC_DIR = REELS_DIR / "music"
POSTED_LOG = BASE_DIR / "posted_reels.txt"
CAPTIONS_JSON = BASE_DIR / "captions.json"
API_BASE = "https://graph.instagram.com/v21.0"

CAPTION_FOOTER = (
    "\n\n📍 New York, NY\n"
    "#newyork #nyc #aiavatar #passiveincome #aibusiness #digitalproducts "
    "#sidehustle #financialfreedom #entrepreneurlife #makemoneyonline"
)
# ────────────────────────────────────────────────────


def load_posted():
    if POSTED_LOG.exists():
        return [l for l in POSTED_LOG.read_text().splitlines() if l.strip()]
    return []


def mark_posted(filename):
    with open(POSTED_LOG, "a") as f:
        f.write(filename + "\n")


def get_next_reel():
    posted = set(load_posted())
    mp4_files = sorted(REELS_DIR.glob("*.mp4"))
    for f in mp4_files:
        if f.name not in posted:
            return f
    return None


def load_captions():
    if CAPTIONS_JSON.exists():
        return json.loads(CAPTIONS_JSON.read_text(encoding="utf-8"))
    return []


def get_caption(reel_path):
    override = reel_path.with_suffix(".txt")
    if override.exists():
        return override.read_text(encoding="utf-8").strip()

    captions = load_captions()
    if captions:
        idx = len(load_posted()) % len(captions)
        body = captions[idx].strip()
        if "📍" not in body and "#" not in body:
            body = body + CAPTION_FOOTER
        return body

    return "Julian | Operator Systems" + CAPTION_FOOTER


def merge_music(reel_path):
    """reels/music/ のBGMを動画にミックス。(merged_path, track_name)を返す。"""
    if not MUSIC_DIR.exists():
        return reel_path, "(none)"
    tracks = sorted(list(MUSIC_DIR.glob("*.mp3")) + list(MUSIC_DIR.glob("*.m4a")) + list(MUSIC_DIR.glob("*.wav")))
    if not tracks:
        print("No music in reels/music/ — posting with original audio only")
        return reel_path, "(none)"

    if not shutil.which("ffmpeg"):
        print("ffmpeg not installed — skipping music merge")
        return reel_path, "(ffmpeg missing)"

    track = random.choice(tracks)
    print(f"Merging music: {track.name}")

    out_path = Path(tempfile.gettempdir()) / f"merged_{reel_path.name}"

    # 元音声 30% + BGM 100% でミックス（元に音声がない動画でもBGMは入る）
    cmd = [
        "ffmpeg", "-y",
        "-i", str(reel_path),
        "-i", str(track),
        "-filter_complex",
        "[0:a]volume=0.3[a0];[1:a]volume=1.0[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=0[aout]",
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(out_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # 元動画に音声トラックがない場合のフォールバック: BGMを直接付ける
        print("  amix failed, falling back to audio-only BGM attach")
        cmd2 = [
            "ffmpeg", "-y",
            "-i", str(reel_path),
            "-i", str(track),
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(out_path),
        ]
        result = subprocess.run(cmd2, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  ffmpeg failed: {result.stderr[-500:]}")
            return reel_path, track.name

    print(f"  Merged -> {out_path}")
    return out_path, track.name


def upload_video_to_public_url(reel_path):
    url = "https://catbox.moe/user/api.php"
    with open(reel_path, "rb") as f:
        resp = requests.post(
            url,
            data={"reqtype": "fileupload"},
            files={"fileToUpload": f},
            timeout=180,
        )
    resp.raise_for_status()
    video_url = resp.text.strip()
    if not video_url.startswith("http"):
        raise Exception(f"Upload failed: {video_url}")
    return video_url


def create_media_container(video_url, caption):
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


def send_email_notification(reel_name, post_id, caption, music_name):
    """Resend経由で投稿完了メールを送る"""
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        print("RESEND_API_KEY not set — skipping email")
        return
    post_url = f"https://www.instagram.com/p/{post_id}/"
    subject = f"[Julian Reels] {reel_name} 投稿完了"
    html = f"""
    <h2>Reels 投稿完了</h2>
    <p><b>ファイル:</b> {reel_name}</p>
    <p><b>投稿ID:</b> {post_id}</p>
    <p><b>BGM:</b> {music_name}</p>
    <p><b>投稿URL:</b> <a href="https://www.instagram.com/thejulianmethod/">@thejulianmethod</a></p>
    <hr>
    <p><b>キャプション:</b></p>
    <pre style="white-space:pre-wrap;font-family:inherit">{caption}</pre>
    """
    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": "Julian Bot <onboarding@resend.dev>",
                "to": "nagashimakentaro116@gmail.com",
                "subject": subject,
                "html": html,
            },
            timeout=30,
        )
        if resp.status_code in (200, 201):
            print(f"Email sent: {resp.json().get('id', '')}")
        else:
            print(f"Email failed: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        print(f"Email exception: {e}")


def main():
    if not IG_TOKEN:
        print("ERROR: INSTAGRAM_ACCESS_TOKEN not set")
        sys.exit(1)

    reel = get_next_reel()
    if not reel:
        print("No new reels to post.")
        return

    original_name = reel.name
    print(f"[{datetime.now().isoformat()}] Posting: {original_name}")

    caption = get_caption(reel)
    print(f"Caption preview: {caption[:80]}...")

    print("Merging music...")
    merged, music_name = merge_music(reel)

    print("Uploading video...")
    video_url = upload_video_to_public_url(merged)
    print(f"Video URL: {video_url}")

    print("Creating media container...")
    container_id = create_media_container(video_url, caption)
    print(f"Container ID: {container_id}")

    print("Waiting for processing...")
    wait_for_container(container_id)

    print("Publishing...")
    post_id = publish_container(container_id)
    print(f"SUCCESS: Published post ID {post_id}")

    mark_posted(original_name)
    print(f"Marked as posted: {original_name}")

    send_email_notification(original_name, post_id, caption, music_name)


if __name__ == "__main__":
    main()
