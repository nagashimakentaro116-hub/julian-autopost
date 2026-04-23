import requests
import schedule
import time
import csv
import os
from datetime import datetime, timedelta
from generate_posts import replenish_if_needed

# ─── 設定読み込み ─────────────────────────────
def load_config():
    config = {}
    config_path = os.path.join(os.path.dirname(__file__), "config.txt")
    with open(config_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                key, _, value = line.partition("=")
                config[key.strip()] = value.strip()
    return config

CONFIG = load_config()
ACCESS_TOKEN = CONFIG.get("THREADS_ACCESS_TOKEN")
USER_ID = CONFIG.get("THREADS_USER_ID")
LOG_FILE = os.path.join(os.path.dirname(__file__), CONFIG.get("LOG_FILE", "autopost_log.txt"))
QUEUE_FILE = os.path.join(os.path.dirname(__file__), "posts_queue.csv")
IMAGES_DIR = os.path.join(os.path.dirname(__file__), "images")
POST_TIMES = [
    CONFIG.get("POST_TIME_1", "21:00"),
    CONFIG.get("POST_TIME_2", "02:00"),
    CONFIG.get("POST_TIME_3", "09:00"),
]

# ─── ログ ──────────────────────────────────────
def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ─── 画像アップロード（freeimage.host） ───────
def upload_image(image_path):
    with open(image_path, "rb") as f:
        res = requests.post(
            "https://freeimage.host/api/1/upload",
            data={"key": "6d207e02198a847aa98d0a2a901485a5"},
            files={"source": f}
        )

    if res.status_code == 200:
        data = res.json()
        url = data["image"]["image"]["url"]
        log(f"画像アップロード成功: {url}")
        return url
    else:
        log(f"ERROR image upload: status={res.status_code} body={res.text[:100]}")
        return None

# ─── キュー操作 ────────────────────────────────
def load_queue():
    posts = []
    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            posts.append(row)
    return posts

def save_queue(posts):
    if not posts:
        return
    fieldnames = posts[0].keys()
    with open(QUEUE_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(posts)

def get_next_pending():
    posts = load_queue()
    for post in posts:
        if post["status"] == "pending":
            return post
    return None

def mark_posted(post_id):
    posts = load_queue()
    for post in posts:
        if post["id"] == str(post_id):
            post["status"] = "posted"
            post["scheduled_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_queue(posts)

# ─── Threads API ───────────────────────────────
def create_container(text, image_url=None):
    url = f"https://graph.threads.net/v1.0/{USER_ID}/threads"
    params = {
        "media_type": "TEXT",
        "text": text,
        "access_token": ACCESS_TOKEN
    }
    if image_url:
        params["media_type"] = "IMAGE"
        params["image_url"] = image_url

    res = requests.post(url, params=params)
    data = res.json()

    if "id" in data:
        return data["id"]
    else:
        log(f"ERROR create_container: {data}")
        return None

def publish_container(container_id):
    url = f"https://graph.threads.net/v1.0/{USER_ID}/threads_publish"
    params = {
        "creation_id": container_id,
        "access_token": ACCESS_TOKEN
    }
    res = requests.post(url, params=params)
    data = res.json()

    if "id" in data:
        return data["id"]
    else:
        log(f"ERROR publish_container: {data}")
        return None

# ─── 投稿メイン処理 ────────────────────────────
def post_next():
    post = get_next_pending()

    if not post:
        log("キューに投稿がありません。posts_queue.csvに追加してください。")
        return

    log(f"投稿開始: ID={post['id']} | {post['text'][:30]}...")

    image_url = None
    image_filename = post.get("image_path", "").strip()

    if image_filename:
        image_full_path = os.path.join(IMAGES_DIR, image_filename)
        if os.path.exists(image_full_path):
            log(f"画像をアップロード中: {image_filename}")
            image_url = upload_image(image_full_path)
        else:
            log(f"WARNING: 画像が見つかりません: {image_full_path} → テキストのみで投稿します")

    container_id = create_container(text=post["text"], image_url=image_url)

    if not container_id:
        log("コンテナ作成失敗。スキップします。")
        return

    time.sleep(3)

    thread_id = publish_container(container_id)

    if thread_id:
        log(f"投稿成功: thread_id={thread_id}")
        mark_posted(post["id"])
    else:
        log("投稿失敗。")

# ─── 起動時の投稿漏れチェック ──────────────────
def check_missed_posts():
    now = datetime.now()
    for t in POST_TIMES:
        h, m = map(int, t.split(":"))
        scheduled = now.replace(hour=h, minute=m, second=0, microsecond=0)
        diff = abs((now - scheduled).total_seconds())
        if diff <= 1800:  # 30分以内なら投稿漏れとみなして即投稿
            log(f"投稿漏れ検出 ({t} JST)。即時投稿します。")
            post_next()
            break

# ─── セットアップ確認 ──────────────────────────
def check_setup():
    if "ここに" in ACCESS_TOKEN or "ここに" in USER_ID:
        print("=" * 50)
        print("【セットアップ未完了】")
        print("config.txtを開いてAccess TokenとUser IDを設定してください。")
        print("=" * 50)
        return False
    return True

# ─── スケジューラー起動 ────────────────────────
def start():
    if not check_setup():
        return

    log(f"スケジューラー起動: 毎日 {POST_TIMES[0]} / {POST_TIMES[1]} / {POST_TIMES[2]} JST に自動投稿 (NY: 7AM / 12PM / 7PM)")
    check_missed_posts()  # 起動時に投稿漏れを確認

    for t in POST_TIMES:
        schedule.every().day.at(t).do(post_next)

    # 毎朝8:00 JSTにキューを自動補充（pending < 6本になったら生成）
    schedule.every().day.at("08:00").do(lambda: replenish_if_needed(threshold=6, generate_count=9))

    # テスト投稿する場合は下の行のコメントを外す
    post_next()

    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    start()
