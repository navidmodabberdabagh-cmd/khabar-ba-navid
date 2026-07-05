# -*- coding: utf-8 -*-
"""خبر با نوید - ربات خبری تلگرام"""
import os, re, json, time, hashlib, random, feedparser, requests
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageFilter
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
PADDING = 55
HIGH_RANKING_COUNTRIES = ["آمریکا", "فرانسه", "آلمان", "اسپانیا", "اسرائیل", "امارات", "قطر", "عربستان", "پاکستان", "ترکیه", "ترامپ", "بایدن", "ماکرون", "شولتز", "نتانیاهو"]
IMPORTANT_TOPICS = {"مهاجرت": ["مهاجرت", "ویزا", "اقامت", "اداره مهاجرت", "پناجران", "پناهندگی"], "رضا پهلوی": ["رضا پهلوی", "شاهزاده", "پهلوی"], "ترامپ_ایران": ["ترامپ", "تحریم ایران", "آمریکا ایران"]}

def load_font(path, size):
    return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.BASIC)

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

def clean_text(text):
    text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    while "  " in text:
        text = text.replace("  ", " ")
    return text.strip()

def shape_text(text):
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)

def apply_replacements(text, original_text):
    text = re.sub(r"(آیت\s*الله|امام)?\s*خامنه\s*ای", "خامنه‌ای", text)
    text = re.sub(r"(آیت\s*الله|امام)?\s*خمینی", "خمینی", text)
    text = text.replace("رهبر شهید", "جسد خامنه‌ای")
    text = text.replace("جمهوری اسلامی ایران", "جمهوری اسلامی")
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
        shaped = shape_text(test)
        w = draw.textlength(shaped, font=font)
        if w <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines

def draw_right_line(draw, text, font, y, fill, width):
    shaped = shape_text(text)
    tw = draw.textlength(shaped, font=font)
    draw.text((width - PADDING - tw, y), shaped, font=font, fill=fill)

def make_background(width, height):
    img = Image.new("RGB", (width, height), "#FFFDF7")
    overlay = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    blobs = [(20, 140, 90, 55), (200, 40, 40, 45), (110, 20, 150, 40), (225, 180, 20, 50)]
    for c in blobs:
        x = random.randint(0, width)
        y = random.randint(0, height)
        r = random.randint(int(width * 0.30), int(width * 0.60))
        draw.ellipse([x - r, y - r, x + r, y + r], fill=c)
    overlay = overlay.filter(ImageFilter.GaussianBlur(60))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    return img

def draw_frame(draw, width, height):
    shades = ["#5C4210", "#B8860B", "#E8C158", "#FFDE7A", "#E8C158", "#B8860B"]
    for i, color in enumerate(shades):
        draw.rectangle([i * 3, i * 3, width - 1 - i * 3, height - 1 - i * 3], outline=color, width=3)

def make_image(source_name, headline_fa, body_fa, important_topic=None):
    source_name = clean_text(source_name)
    headline_fa = clean_text(headline_fa)
    body_fa = clean_text(body_fa)

    dummy = Image.new("RGB", (10, 10))
    d = ImageDraw.Draw(dummy)

    source_font = load_font(FONT_BOLD, 50)
    headline_font = load_font(FONT_BOLD, 46)
    body_font = load_font(FONT_REGULAR, 40)
    footer_font = load_font(FONT_BOLD, 40)
    important_font = load_font(FONT_BOLD, 70)

    max_w = IMG_WIDTH - 2 * PADDING
    headline_lines = wrap_text(headline_fa, headline_font, max_w, d)
    body_lines = wrap_text(body_fa, body_font, max_w, d)

    top_area = PADDING + 62 + 10 + len(headline_lines) * 58 + 20
    body_height = len(body_lines) * 58
    footer_height = 100
    total_height = max(top_area + body_height + footer_height, IMG_HEIGHT)

    img = make_background(IMG_WIDTH, total_height)
    draw = ImageDraw.Draw(img)

    y = PADDING
    draw_right_line(draw, source_name, source_font, y, "#111111", IMG_WIDTH)
    y += 62 + 10

    for line in headline_lines:
        draw_right_line(draw, line, headline_font, y, "#0B7A3D", IMG_WIDTH)
        y += 58
    y += 20

    for line in body_lines:
        draw_right_line(draw, line, body_font, y, "#1A1A1A", IMG_WIDTH)
        y += 58

    footer_text = "خبر با نوید"
    shaped_footer = shape_text(footer_text)
    fw = draw.textlength(shaped_footer, font=footer_font)
    draw.text(((IMG_WIDTH - fw) / 2, total_height - footer_height + 25), shaped_footer, font=footer_font, fill="#00695C")

    if important_topic:
        draw.text((IMG_WIDTH - 110, 25), "⚠️", font=important_font, fill="#C8102E")

    draw_frame(draw, IMG_WIDTH, total_height)

    path = "temp_news.jpg"
    img.save(path, quality=92)
    return path

def send_photo(image_path, caption=""):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    with open(image_path, "rb") as photo:
        resp = requests.post(url, data={"chat_id": CHAT_ID, "caption": caption}, files={"photo": photo})
    if not resp.ok:
        print(f"خطا: {resp.text}")
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
            title = clean_text(entry.get("title", ""))
            summary = clean_text(re.sub("<[^<]+?>", "", entry.get("summary", "")))[:400]
            original_full = f"{title}. {summary}"

            headline_fa = clean_text(translate_to_persian(title))
            body_fa = clean_text(translate_to_persian(summary)) if summary else ""

            headline_fa = apply_replacements(headline_fa, original_full)
            body_fa = apply_replacements(body_fa, original_full)

            important_topic = detect_important_topic(original_full + " " + headline_fa + " " + body_fa)
            img_path = make_image(source_name, headline_fa, body_fa, important_topic)
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
