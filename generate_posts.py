import anthropic
import csv
import os
import json
from datetime import datetime

# config.txtからAPIキーを読み込む
def _get_api_key():
    config_path = os.path.join(os.path.dirname(__file__), "config.txt")
    with open(config_path, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None

os.environ["ANTHROPIC_API_KEY"] = _get_api_key() or ""

QUEUE_FILE = os.path.join(os.path.dirname(__file__), "posts_queue.csv")
IMAGES_DIR = os.path.join(os.path.dirname(__file__), "images")
LOG_FILE = os.path.join(os.path.dirname(__file__), "autopost_log.txt")

# ─── ログ ──────────────────────────────────────
def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ─── キュー操作 ────────────────────────────────
def load_queue():
    if not os.path.exists(QUEUE_FILE):
        return []
    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def save_queue(posts):
    if not posts:
        return
    with open(QUEUE_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=posts[0].keys())
        writer.writeheader()
        writer.writerows(posts)

def count_pending():
    posts = load_queue()
    return sum(1 for p in posts if p["status"] == "pending")

def get_next_id():
    posts = load_queue()
    if not posts:
        return 1
    return max(int(p["id"]) for p in posts) + 1

def get_available_images():
    if not os.path.exists(IMAGES_DIR):
        return []
    return [f for f in os.listdir(IMAGES_DIR)
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]

def get_used_images():
    posts = load_queue()
    return [p["image_path"] for p in posts if p.get("image_path")]

# ─── Claude API で投稿生成 ─────────────────────
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

COMPETITOR BENCHMARKS (what's already out there — be DIFFERENT):
- @baddieinbiz: bright, emoji-heavy, educational listicles → Julian is darker, quieter, more premium
- @itsolivia.ai: casual, friendly, questions → Julian is authoritative, declarative
- Generic AI income posts: hype, "$300/day" claims → Julian is understated, proof-based

CONTENT TYPES THAT WORK (rotate through these):
1. Declarative: Bold single truth statement
2. Contrast: "Most people X. Operators Y."
3. List: "3 things operators never do: —"
4. Reveal: Exposing Julian as AI, humanizing the system
5. Proof: Reference to real numbers ($6,813, $147, built in one afternoon)
6. Philosophy: Short wisdom about ownership vs. effort
7. Question: Single open question to drive replies
"""

def generate_posts(count=9):
    client = anthropic.Anthropic()

    log(f"Claude APIで投稿文{count}本を生成中...")

    prompt = f"""Generate {count} unique Threads posts for Julian.

Return ONLY a JSON array. No explanation, no markdown, just raw JSON.

Format:
[
  {{"text": "post text here\\n\\nLink in bio.", "type": "declarative"}},
  ...
]

Requirements:
- Each post must be a different content type (declarative, contrast, list, reveal, proof, philosophy, question)
- No duplicate hooks or themes
- Each post must end with "Link in bio." on its own line (except question type)
- Maximum 6 lines per post
- Sound like a premium American brand, not a course seller
"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=BRAND_GUIDELINES,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()

    # JSONを抽出
    if raw.startswith("["):
        posts_data = json.loads(raw)
    else:
        start = raw.find("[")
        end = raw.rfind("]") + 1
        posts_data = json.loads(raw[start:end])

    log(f"{len(posts_data)}本の投稿文を生成しました")
    return posts_data

# ─── 品質チェック ──────────────────────────────
def quality_check(posts_data):
    client = anthropic.Anthropic()

    log("投稿添削者: 品質チェック中...")

    posts_json = json.dumps(posts_data, ensure_ascii=False)

    prompt = f"""Review these Threads posts for Julian and return only the approved ones.

Posts to review:
{posts_json}

Reject a post if:
- Contains emojis
- Contains exclamation marks
- Sounds like hype or a course seller
- Uses banned words: hustle, grind, guru, hack, secret, amazing, incredible
- Doesn't sound like native American English
- Missing "Link in bio." (except question type)

For approved posts, you may slightly improve the wording if needed.

Return ONLY a JSON array of approved posts in the same format. No explanation.
"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=BRAND_GUIDELINES,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()

    if raw.startswith("["):
        approved = json.loads(raw)
    else:
        start = raw.find("[")
        end = raw.rfind("]") + 1
        approved = json.loads(raw[start:end])

    log(f"品質チェック完了: {len(approved)}/{len(posts_data)}本 承認")
    return approved

# ─── キューに追加 ──────────────────────────────
def add_to_queue(approved_posts):
    posts = load_queue()
    available_images = get_available_images()
    used_images = get_used_images()

    unused_images = [img for img in available_images if img not in used_images]
    if not unused_images:
        unused_images = available_images  # 全部使い終わったらローテーション

    next_id = get_next_id()
    img_index = 0

    for post_data in approved_posts:
        image = ""
        if unused_images and img_index < len(unused_images):
            image = unused_images[img_index]
            img_index += 1

        new_post = {
            "id": str(next_id),
            "text": post_data["text"],
            "image_path": image,
            "status": "pending",
            "scheduled_time": "auto"
        }
        posts.append(new_post)
        next_id += 1

    save_queue(posts)
    log(f"{len(approved_posts)}本をキューに追加しました (pending合計: {count_pending()})")

# ─── メイン: キュー補充 ────────────────────────
def replenish_if_needed(threshold=6, generate_count=9):
    pending = count_pending()
    log(f"キュー確認: pending={pending}本")

    if pending >= threshold:
        log(f"キュー十分 ({pending}本)。生成スキップ。")
        return

    log(f"キュー不足 ({pending}本 < {threshold}本)。補充開始。")

    try:
        posts_data = generate_posts(generate_count)
        approved = quality_check(posts_data)
        add_to_queue(approved)
    except Exception as e:
        log(f"ERROR 投稿生成失敗: {e}")

if __name__ == "__main__":
    replenish_if_needed(threshold=6, generate_count=9)
