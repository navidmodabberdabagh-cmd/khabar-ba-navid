# -*- coding: utf-8 -*-
"""خبر با نوید - ربات خبری تلگرام"""
import os, re, json, time, hashlib, feedparser, requests
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from deep_translator import GoogleTranslator
import arabic_reshaper
from bidi.algorithm import get_display
from sources import RSS_FEEDS, KEYWORDS

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SENT_IDS_FILE = "sent_ids.json"
MAX_SEND_PER_RUN = 6
RUN_DURATION_SECONDS = int(os.environ.get("RUN_DURATION_SECONDS", "1500"))
CHECK_INTERVAL_SECONDS = 90
FONT_BOLD = "fonts/Vazirmatn-Bold.ttf"
FONT_REGULAR = "fonts/Vazirmatn-Regular.ttf"
IMG_WIDTH, IMG_HEIGHT = 1080, 1920
BANNER_HEIGHT, FOOTER_HEIGHT, PADDING = 180, 80, 50
HIGH_RANKING_COUNTRIES = ["آمریکا", "فرانسه", "آلمان", "اسپانیا", "اسرائیل", "امارات", "قطر", "عربستان", "پاکستان", "ترکیه", "ترامپ", "بایدن", "ماکرون", "شولتز", "نتانیاهو"]
IMPORTANT_TOPICS = {
    "مهاجرت": ["مهاجرت", "ویزا", "اقامت", "اداره مهاجرت", "پناجران", "پناهندگی"],
    "رضا پهلوی": ["رضا پهلوی", "شاهزاده", "پهلوی"],
    "ترامپ_ایران": ["ترامپ", "تحریم ایران", "آمریکا ایران"]
}

def load_sent_ids():
    if os.path.exists(SENT_IDS_FILE):
        with open(SENT_IDS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_sent_ids(ids):
    ids_list = list(ids)[-500:]
    with open(SENT_IDS_FILE, "w", encoding="utf-8") as f:
        json.dump(ids_list, f, ensure_ascii=False)

def item_id(entry):
    raw = entry.get("id") or entry.get("link") or entry.get("title", "")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def is_relevant(entry):
    text = (entry.get("title", "") + " " + entry.get("summary", "")).lower()
    return any(kw.lower() in text for kw in KEYWORDS)

def translate_to_persian(text):
    try:
        return GoogleTranslator(source="auto", target="fa").translate(text)
    except:
        return text

def shape_persian(text):
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)

def apply_replacements(text, original_text):
    text = re.sub(r"(آیت\s*الله|امام)?\s*خامنه\s*ای", "خامنه‌ای", text)
    text = re.sub(r"(آیت\s*الله|امام)?\s*خمینی", "خمینی", text)
    has_high_ranking = any(country.lower() in original_text.lower() for country in HIGH_RANKING_COUNTRIES)
    if not has_high_ranking:
        text = re.sub(r"آیت\s*الله\s+(\w+)", r"آقای \1", text)
        text = re.sub(r"امام\s+(\w+)", r"آقای \1", text)
    return text

def detect_important_topic(text):
    text_lower = text.lower()
    for topic, keywords in IMPORTANT_TOPICS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                return topic
    return None

def wrap_text(text, font, max_width, draw):
    words = text.split(" ")
    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        w = draw.textlength(shape_persian(test), font=font)
        if w <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines

def make_image(source_name, persian_text, important_topic=None):
    dummy_img = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(dummy_img)
    body_font = ImageFont.truetype(FONT_REGULAR, 42)
    banner_font = ImageFont.truetype(FONT_BOLD, 58)
    footer_font = ImageFont.truetype(FONT_REGULAR, 28)
    important_font = ImageFont.truetype(FONT_BOLD, 72)
    max_text_width = IMG_WIDTH - 2 * PADDING
    lines = wrap_text(persian_text, body_font, max_text_width, draw)
    line_height = 60
    body_height = len(lines) * line_height + 2 * PADDING
    total_height = max(BANNER_HEIGHT + body_height + FOOTER_HEIGHT, IMG_HEIGHT)
    img = Image.new("RGB", (IMG_WIDTH, total_height), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, IMG_WIDTH, BANNER_HEIGHT], fill="#C8102E")
    source_shaped = shape_persian(source_name)
    sw = draw.textlength(source_shaped, font=banner_font)
    draw.text(((IMG_WIDTH - sw) / 2, (BANNER_HEIGHT - 58) / 2), source_shaped, font=banner_font, fill="white")
    y = BANNER_HEIGHT + PADDING
    for line in lines:
        shaped = shape_persian(line)
        lw = draw.textlength(shaped, font=body_font)
        draw.text((IMG_WIDTH - PADDING - lw, y), shaped, font=body_font, fill="black")
        y += line_height
    footer_text = shape_persian("خبر با نوید")
    fw = draw.textlength(footer_text, font=footer_font)
    draw.text(((IMG_WIDTH - fw) / 2, total_height - FOOTER_HEIGHT + 15), footer_text, font=footer_font, fill="#888888")
    if important_topic:
        draw.text((IMG_WIDTH - 100, 20), "⚠️", font=important_font, fill="#C8102E")
    path = "temp_news.jpg"
    img.save(path, quality=90)
    return path

def send_photo(image_path, caption=""):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    with open(image_path, "rb") as photo:
        resp = requests.post(url, data={"chat_id": CHAT_ID, "caption": caption}, files={"photo": photo})
    if not resp.ok:
        print(f"خطا در ارسال: {resp.text}")
    return resp.ok

def fetch_and_process(sent_ids):
    sent_count = 0
    for source_name, feed_url in RSS_FEEDS.items():
        if sent_count >= MAX_SEND_PER_RUN:
            break
        try:
            feed = feedparser.parse(feed_url)
        except Exception as e:
            print(f"خطا در {source_name}: {e}")
            continue
        for entry in feed.entries[:15]:
            if sent_count >= MAX_SEND_PER_RUN:
                break
            eid = item_id(entry)
            if eid in sent_ids or not is_relevant(entry):
                continue
            title = entry.get("title", "")
            summary = re.sub("<[^<]+?>", "", entry.get("summary", ""))[:400]
            original_text = f"{title}. {summary}".strip()
            persian_text = translate_to_persian(original_text)
            persian_text = apply_replacements(persian_text, original_text)
            important_topic = detect_important_topic(original_text + " " + persian_text)
            img_path = make_image(source_name, persian_text, important_topic)
            ok = send_photo(img_path, caption=entry.get("link", ""))
            if ok:
                sent_ids.add(eid)
                sent_count += 1
                print(f"ارسال شد: {source_name} -> {title[:50]}")
            time.sleep(2)
    return sent_ids

def main():
    print(f"شروع اجرا در {datetime.now()}")
    if not BOT_TOKEN or not CHAT_ID:
        print("لطفاً TELEGRAM_BOT_TOKEN و TELEGRAM_CHAT_ID را تنظیم کنید.")
        return
    sent_ids = load_sent_ids()
    start = time.time()
    while time.time() - start < RUN_DURATION_SECONDS:
        sent_ids = fetch_and_process(sent_ids)
        save_sent_ids(sent_ids)
        time.sleep(CHECK_INTERVAL_SECONDS)
    print("پایان اجرا.")

if __name__ == "__main__":
    main()
