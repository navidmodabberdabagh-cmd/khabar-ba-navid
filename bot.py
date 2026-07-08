# -*- coding: utf-8 -*-
"""خبر با نوید - ربات خبری تلگرام"""
import os, re, json, time, hashlib, random, feedparser, requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from deep_translator import GoogleTranslator
import arabic_reshaper
from bidi.algorithm import get_display
from sources import (RSS_FEEDS, KEYWORDS, WEATHER_ALLOWED_LOCATIONS,
                      WEATHER_SEVERITY_WORDS, MEDICAL_SOURCES)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OWNER_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SENT_IDS_FILE = "sent_ids.json"
CHAT_IDS_FILE = "chat_ids.json"
OFFSET_FILE = "update_offset.json"
MAX_SEND_PER_RUN = 1000
RUN_DURATION_SECONDS = int(os.environ.get("RUN_DURATION_SECONDS", "1500"))
CHECK_INTERVAL_SECONDS = 60
FEED_TIMEOUT = 10
TRANSLATE_TIMEOUT = 12
FONT_BOLD = "fonts/Vazirmatn-Bold.ttf"
FONT_REGULAR = "fonts/Vazirmatn-Regular.ttf"
IMG_WIDTH, IMG_HEIGHT = 1080, 1920
PADDING = 55
BANNER_HEIGHT = 190

WELCOME_TEXT = """🎉 خوش‌آمدید به ربات خبری «خبر با نوید»

📰 این ربات توسط نوید مدبر ساخته شده و هر روز اخبار مرتبط با ایران و منطقه را می‌فرستد.

📱 پیج اینستاگرام: @nm_est

🔔 اخبار لحظه‌ای هر روز"""

COUNTRY_WATERMARKS = {
    "ترکیه": {"color": (200, 30, 30), "flag": True},
    "ایران": {"color": None, "flag": False, "special": "iran"},
    "روسیه": {"color": (190, 190, 190), "flag": False},
    "اوکراین": {"color": (70, 180, 70), "flag": False},
    "آمریکا": {"color": (130, 130, 130), "flag": True},
    "اسرائیل": {"color": (60, 90, 190), "flag": True},
    "چین": {"color": (190, 30, 30), "flag": True},
}
COUNTRY_KEYWORDS = {
    "ترکیه": ["ترکیه", "turkey", "استانبول", "آنکارا"],
    "ایران": ["ایران", "iran", "تهران"],
    "روسیه": ["روسیه", "russia"],
    "اوکراین": ["اوکراین", "اکراین", "ukraine"],
    "آمریکا": ["آمریکا", "امریکا", "america", "united states", "واشنگتن"],
    "اسرائیل": ["اسرائیل", "israel"],
    "چین": ["چین", "china"],
}
FOOTBALL_WORDS = ["فوتبال", "football", "جام جهانی", "world cup", "لیگ", "team melli", "گل زد"]

_executor = ThreadPoolExecutor(max_workers=4)


def run_with_timeout(func, args=(), timeout=10, default=None):
    future = _executor.submit(func, *args)
    try:
        return future.result(timeout=timeout)
    except Exception:
        return default


def load_font(path, size):
    return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.BASIC)


def load_json_set(path, default_list):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return set(str(x) for x in json.load(f))
    return set(str(x) for x in default_list if x)


def save_json_set(path, s):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(list(s)[-2000:], f, ensure_ascii=False)


def load_offset():
    if os.path.exists(OFFSET_FILE):
        with open(OFFSET_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("offset", 0)
    return 0


def save_offset(offset):
    with open(OFFSET_FILE, "w", encoding="utf-8") as f:
        json.dump({"offset": offset}, f)


def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=15)
    except Exception as e:
        print(f"خطا در ارسال پیام به {chat_id}: {e}")


def poll_new_starters(chat_ids):
    offset = load_offset()
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    try:
        resp = requests.get(url, params={"offset": offset, "timeout": 0}, timeout=15)
        data = resp.json()
    except Exception as e:
        print(f"خطا در getUpdates: {e}")
        return chat_ids
    updates = data.get("result", [])
    new_offset = offset
    for u in updates:
        new_offset = max(new_offset, u.get("update_id", 0) + 1)
        msg = u.get("message") or u.get("my_chat_member", {}).get("chat")
        if not msg:
            continue
        chat_obj = msg.get("chat") if isinstance(msg, dict) and "chat" in msg else msg
        if not chat_obj or "id" not in chat_obj:
            continue
        cid = str(chat_obj["id"])
        if cid not in chat_ids:
            chat_ids.add(cid)
            send_message(cid, WELCOME_TEXT)
            print(f"چت جدید اضافه شد: {cid}")
    if new_offset > offset:
        save_offset(new_offset)
    return chat_ids


def item_id(entry):
    raw = entry.get("id") or entry.get("link") or entry.get("title", "")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_entry_text(entry):
    parts = []
    for key in ["title", "summary", "description"]:
        val = entry.get(key, "")
        if val:
            parts.append(str(val))
    if "summary_detail" in entry and isinstance(entry["summary_detail"], dict):
        parts.append(str(entry["summary_detail"].get("value", "")))
    if "content" in entry:
        for c in entry.get("content", []):
            parts.append(str(c.get("value", "")))
    return " ".join(parts)


def is_relevant(entry):
    text = get_entry_text(entry).lower()
    return any(kw.lower() in text for kw in KEYWORDS)


def passes_weather_filter(full_text):
    is_weather = any(w in full_text for w in WEATHER_SEVERITY_WORDS)
    if not is_weather:
        return True
    return any(loc in full_text for loc in WEATHER_ALLOWED_LOCATIONS)


def _do_translate(text):
    return GoogleTranslator(source="auto", target="fa").translate(text)


def translate_to_persian(text):
    result = run_with_timeout(_do_translate, (text,), TRANSLATE_TIMEOUT, default=None)
    return result if result else text


def clean_text(text):
    text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    while "  " in text:
        text = text.replace("  ", " ")
    return text.strip()


def shape_text(text):
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)


def apply_replacements(text):
    text = re.sub(r"آیت\s*[-‌]?\s*الله\s*", "", text)
    text = re.sub(r"(^|\s)امام\s+خامنه", r"\1خامنه", text)
    text = re.sub(r"(^|\s)امام\s+خمینی", r"\1خمینی", text)
    text = text.replace("رهبر شهید", "جسد خامنه‌ای")
    text = text.replace("جمهوری اسلامی ایران", "جمهوری اسلامی")
    text = text.replace("رژیم صهیونیستی", "اسرائیل")
    text = text.replace("شهدای لبنان", "کشته‌شدگان لبنانی")
    return clean_text(text)


def detect_football(text):
    t = text.lower()
    return any(w.lower() in t for w in FOOTBALL_WORDS)


def detect_medical(source_name, text):
    if source_name in MEDICAL_SOURCES:
        return True
    med_words = ["cancer", "درمان سرطان", "immunotherapy", "desalination", "آب شیرین‌سازی"]
    t = text.lower()
    return any(w.lower() in t for w in med_words)


def detect_country(text):
    for country, kws in COUNTRY_KEYWORDS.items():
        if any(kw.lower() in text.lower() for kw in kws):
            return country
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


def draw_center_line(draw, text, font, y, fill, stroke_fill, width):
    shaped = shape_text(text)
    tw = draw.textlength(shaped, font=font)
    x = (width - tw) / 2
    draw.text((x, y), shaped, font=font, fill=fill, stroke_width=3, stroke_fill=stroke_fill)


def make_compass_rose(size, color=(197, 168, 103, 130)):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2
    r = size // 2 - 5
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=2)
    d.ellipse([cx - r * 0.6, cy - r * 0.6, cx + r * 0.6, cy + r * 0.6], outline=color, width=1)
    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        x2 = cx + r * 0.95 * math.sin(rad)
        y2 = cy - r * 0.95 * math.cos(rad)
        d.line([cx, cy, x2, y2], fill=color, width=2)
    pts = []
    for angle in range(0, 360, 90):
        rad = math.radians(angle)
        pts.append((cx + r * 0.5 * math.sin(rad), cy - r * 0.5 * math.cos(rad)))
    d.polygon(pts, outline=color, width=2)
    return img


def make_geo_mesh(width, height, color=(197, 168, 103, 80), point_count=22):
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pts = [(random.randint(0, width), random.randint(0, height)) for _ in range(point_count)]
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            if random.random() < 0.12:
                d.line([pts[i], pts[j]], fill=color, width=1)
    return img


def make_premium_background(width, height):
    base = Image.new("RGB", (width, height), (10, 32, 34))
    top_c, bottom_c = (8, 26, 28), (16, 44, 46)
    px = base.load()
    for y in range(height):
        t = y / height
        r = int(top_c[0] + (bottom_c[0] - top_c[0]) * t)
        g = int(top_c[1] + (bottom_c[1] - top_c[1]) * t)
        b = int(top_c[2] + (bottom_c[2] - top_c[2]) * t)
        for x in range(0, width, 4):
            for xx in range(x, min(x + 4, width)):
                px[xx, y] = (r, g, b)
    img = base.convert("RGBA")

    compass = make_compass_rose(int(width * 0.34))
    img.paste(compass, (int(-width * 0.06), int(height * 0.02)), compass)

    mesh1 = make_geo_mesh(int(width * 0.5), int(height * 0.22), point_count=18)
    img.paste(mesh1, (int(width * 0.55), 0), mesh1)

    mesh2 = make_geo_mesh(int(width * 0.45), int(height * 0.18), point_count=14)
    img.paste(mesh2, (0, height - int(height * 0.18)), mesh2)

    mesh3 = make_geo_mesh(int(width * 0.4), int(height * 0.16), point_count=14)
    img.paste(mesh3, (width - int(width * 0.4), height - int(height * 0.16)), mesh3)

    return img.convert("RGB")


def draw_glass_card(img, x, y, w, h):
    radius = 40
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card)
    cd.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=(150, 180, 185, 55))
    streak = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(streak)
    sd.line([(w * 0.15, 0), (w * 0.55, h)], fill=(255, 255, 255, 35), width=int(w * 0.12))
    streak = streak.filter(ImageFilter.GaussianBlur(30))
    card = Image.alpha_composite(card, streak)
    bd = ImageDraw.Draw(card)
    bd.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, outline=(220, 190, 120, 170), width=2)
    img.paste(card, (x, y), card)


def draw_football_icon(img, x_center, y_bottom):
    size = 160
    icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(icon)
    d.pieslice([0, 0, size * 2, size * 2], 180, 270, fill=(240, 240, 240, 210))
    d.arc([0, 0, size * 2, size * 2], 180, 270, fill=(20, 20, 20, 230), width=4)
    for i in range(3):
        d.line([(size * 0.2 + i * 15, size * 0.15), (size * 0.35 + i * 15, size * 0.4)],
               fill=(20, 20, 20, 200), width=3)
    icon = icon.filter(ImageFilter.GaussianBlur(1.5))
    img.paste(icon, (x_center - size, y_bottom - size), icon)


def draw_medical_icon(img, x_left, y_bottom):
    size = 150
    icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(icon)
    d.arc([20, 10, size - 20, size - 40], 30, 330, fill=(200, 200, 200, 200), width=6)
    d.ellipse([size // 2 - 15, size - 55, size // 2 + 15, size - 25], outline=(200, 200, 200, 200), width=5)
    icon = icon.filter(ImageFilter.GaussianBlur(2.0))
    img.paste(icon, (x_left, y_bottom - size), icon)


def draw_country_watermark(img, country, width, total_height):
    info = COUNTRY_WATERMARKS.get(country)
    if not info:
        return
    size = 260
    blob = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(blob)
    if info.get("special") == "iran":
        d.pieslice([0, 0, size, size // 3], 0, 360, fill=(0, 150, 60, 90))
        d.pieslice([0, size // 3, size, 2 * size // 3], 0, 360, fill=(240, 240, 240, 90))
        d.pieslice([0, 2 * size // 3, size, size], 0, 360, fill=(200, 20, 20, 90))
    else:
        color = info["color"] + (100,)
        d.ellipse([0, 0, size, size], fill=color)
        if info.get("flag"):
            d.rectangle([size * 0.3, size * 0.3, size * 0.7, size * 0.4],
                        fill=(255, 255, 255, 60))
    blob = blob.filter(ImageFilter.GaussianBlur(14))
    x = width - size + 40
    y = total_height - size + 60
    img.paste(blob, (x, y), blob)


def make_image(source_name, headline_fa, body_fa, full_check_text):
    source_name = clean_text(source_name)
    headline_fa = clean_text(headline_fa)
    body_fa = clean_text(body_fa)

    dummy = Image.new("RGB", (10, 10))
    d = ImageDraw.Draw(dummy)

    source_font = load_font(FONT_REGULAR, 30)
    headline_font = load_font(FONT_BOLD, 54)
    body_font = load_font(FONT_REGULAR, 40)
    brand_font = load_font(FONT_BOLD, 46)
    insta_font = load_font(FONT_REGULAR, 32)

    card_margin_x = 90
    card_w = IMG_WIDTH - 2 * card_margin_x
    inner_pad = 60
    max_w = card_w - 2 * inner_pad

    headline_lines = wrap_text(headline_fa, headline_font, max_w, d)
    body_lines = wrap_text(body_fa, body_font, max_w, d) if body_fa else []

    card_content_h = 70 + len(headline_lines) * 70 + 25 + len(body_lines) * 60 + 90
    card_h = max(card_content_h, 900)

    top_margin = 180
    footer_h = 260
    total_height = max(top_margin + card_h + footer_h, IMG_HEIGHT)

    img = make_premium_background(IMG_WIDTH, total_height).convert("RGBA")
    card_x, card_y = card_margin_x, top_margin
    draw_glass_card(img, card_x, card_y, card_w, card_h)

    draw = ImageDraw.Draw(img, "RGBA")

    y = card_y + 70
    for line in headline_lines:
        shaped = shape_text(line)
        tw = draw.textlength(shaped, font=headline_font)
        x = card_x + (card_w - tw) / 2
        draw.text((x, y), shaped, font=headline_font, fill=(0, 150, 65, 255),
                   stroke_width=3, stroke_fill=(0, 0, 0, 255))
        y += 70

    y += 25
    for line in body_lines:
        shaped = shape_text(line)
        tw = draw.textlength(shaped, font=body_font)
        x = card_x + (card_w - tw) / 2
        draw.text((x, y), shaped, font=body_font, fill=(255, 255, 255, 255),
                   stroke_width=3, stroke_fill=(0, 0, 0, 255))
        y += 60

    source_line = shape_text(f"خبرگذاری: {source_name}")
    draw.text((card_x + inner_pad, card_y + card_h - 70), source_line, font=source_font,
              fill=(220, 220, 220, 255), stroke_width=2, stroke_fill=(0, 0, 0, 255))

    footer_y = card_y + card_h + 50
    shaped_brand = shape_text("خبر با نوید")
    bw = draw.textlength(shaped_brand, font=brand_font)
    draw.text(((IMG_WIDTH - bw) / 2, footer_y + 60), shaped_brand, font=brand_font,
              fill=(230, 120, 60, 255))

    insta_text = "Instagram : @NM_EST"
    iw = draw.textlength(insta_text, font=insta_font)
    draw.text(((IMG_WIDTH - iw) / 2, footer_y), insta_text, font=insta_font,
              fill=(210, 210, 210, 255))

    if detect_football(full_check_text):
        draw_football_icon(img, IMG_WIDTH - 40, total_height - 30)
    elif detect_medical(source_name, full_check_text):
        draw_medical_icon(img, 40, total_height - 30)
    else:
        country = detect_country(full_check_text)
        if country:
            draw_country_watermark(img, country, IMG_WIDTH, total_height)

    img = img.convert("RGB")
    path = "temp_news.jpg"
    img.save(path, quality=92)
    return path

def send_photo_to_all(chat_ids, image_path, caption=""):
    ok_any = False
    for cid in chat_ids:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        try:
            with open(image_path, "rb") as photo:
                resp = requests.post(url, data={"chat_id": cid, "caption": caption},
                                      files={"photo": photo}, timeout=30)
            if resp.ok:
                ok_any = True
            else:
                print(f"خطا در ارسال به {cid}: {resp.text}")
        except Exception as e:
            print(f"خطا در ارسال به {cid}: {e}")
    return ok_any


def _do_fetch(feed_url):
    resp = requests.get(feed_url, timeout=FEED_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
    return feedparser.parse(resp.content)


def fetch_feed_safe(feed_url):
    return run_with_timeout(_do_fetch, (feed_url,), FEED_TIMEOUT + 5, default=None)


def fetch_and_process(sent_ids, chat_ids, deadline):
    sent_count = 0
    for source_name, feed_url in RSS_FEEDS.items():
        if sent_count >= MAX_SEND_PER_RUN or time.time() > deadline:
            break
        feed = fetch_feed_safe(feed_url)
        if not feed or not getattr(feed, "entries", None):
            continue
        for entry in feed.entries[:15]:
            if sent_count >= MAX_SEND_PER_RUN or time.time() > deadline:
                break
            eid = item_id(entry)
            if eid in sent_ids or not is_relevant(entry):
                continue
            title = clean_text(entry.get("title", ""))
            summary = clean_text(re.sub("<[^<]+?>", "", get_entry_text(entry)))[:400]
            original_full = f"{title}. {summary}"

            headline_fa = translate_to_persian(title)
            body_fa = translate_to_persian(summary) if summary else ""

            headline_fa = apply_replacements(headline_fa)
            body_fa = apply_replacements(body_fa)

            full_check = original_full + " " + headline_fa + " " + body_fa

            if not passes_weather_filter(full_check):
                sent_ids.add(eid)
                continue

            try:
                img_path = make_image(source_name, headline_fa, body_fa, full_check)
                caption_text = (f"{headline_fa}\n\n{body_fa}\n\nInstagram: @NM_EST"
                                 if body_fa else f"{headline_fa}\n\nInstagram: @NM_EST")
                ok = send_photo_to_all(chat_ids, img_path, caption_text)
                if ok:
                    sent_ids.add(eid)
                    sent_count += 1
                    save_json_set(SENT_IDS_FILE, sent_ids)
                    print(f"ارسال شد: {source_name} -> {title[:50]}")
            except Exception as e:
                print(f"❌ خطا در ساخت/ارسال عکس برای {source_name}: {e}")
            time.sleep(2)
    return sent_ids


def main():
    print(f"شروع اجرا در {datetime.now()}")
    if not BOT_TOKEN:
        print("لطفاً TELEGRAM_BOT_TOKEN را تنظیم کنید.")
        return
    chat_ids = load_json_set(CHAT_IDS_FILE, [OWNER_CHAT_ID])
    sent_ids = load_json_set(SENT_IDS_FILE, [])
    print(f"تعداد چت‌های فعلی: {len(chat_ids)}")
    start = time.time()
    hard_deadline = start + RUN_DURATION_SECONDS
    while time.time() - start < RUN_DURATION_SECONDS:
        chat_ids = poll_new_starters(chat_ids)
        save_json_set(CHAT_IDS_FILE, chat_ids)
        sent_ids = fetch_and_process(sent_ids, chat_ids, hard_deadline)
        time.sleep(CHECK_INTERVAL_SECONDS)
    print("پایان اجرا.")


if __name__ == "__main__":
    main()
