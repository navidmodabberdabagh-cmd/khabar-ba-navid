# -*- coding: utf-8 -*-
"""خبر با نوید - ربات خبری تلگرام"""
import os, re, json, time, hashlib, random, feedparser, requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from deep_translator import GoogleTranslator
import arabic_reshaper
from bidi.algorithm import get_display
from sources import RSS_FEEDS, KEYWORDS

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
SUMMARY_MAX_CHARS = 900
FONT_BOLD = "fonts/Vazirmatn-Bold.ttf"
FONT_REGULAR = "fonts/Vazirmatn-Regular.ttf"
IMG_WIDTH, IMG_HEIGHT = 1080, 1920
PADDING = 55
BANNER_HEIGHT = 190

HIGH_RANKING_COUNTRIES = ["آمریکا", "فرانسه", "آلمان", "اسپانیا", "اسرائیل", "امارات", "قطر", "عربستان", "پاکستان", "ترکیه", "ترامپ", "بایدن", "ماکرون", "شولتز", "نتانیاهو"]
IMPORTANT_TOPICS = {"مهاجرت": ["مهاجرت", "ویزا", "اقامت", "اداره مهاجرت", "پناجران", "پناهندگی"], "رضا پهلوی": ["رضا پهلوی", "شاهزاده", "پهلوی"], "ترامپ_ایران": ["ترامپ", "تحریم ایران", "آمریکا ایران"]}
WAR_COUNTRIES = ["اسرائیل", "آمریکا", "امارات", "بحرین", "عربستان", "ترکیه", "عراق"]

WELCOME_TEXT = """🎉 خوش‌آمدید به ربات خبری «خبر با نوید»

📰 این ربات توسط نوید مدبر ساخته شده و هر روز اخبار مرتبط با ایران و منطقه را می‌فرستد. شما می‌توانید بدون سانسور یا نگاه جانبدارانه تمام خبرها را بخوانید از تمام خبرگذاری‌های جهان

📚 موضوعات خبری:
✓ مهاجرت و ویزا
✓ اخبار سیاسی و نظامی
✓ فوتبال و ورزش
✓ بورس و اقتصاد
✓ و غیره...

⚠️ علامت قرمز = موضوع مهم (مهاجرت، رضا پهلوی، ترامپ، جنگ)

📱 پیج اینستاگرام: @nm_est
(آژانس املاک و سرمایه‌گذاری در ترکیه)

🔔 اخبار لحظه‌ای هر روز"""

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
        msg = u.get("message")
        if not msg:
            continue
        cid = str(msg["chat"]["id"])
        if cid not in chat_ids:
            chat_ids.add(cid)
            send_message(cid, WELCOME_TEXT)
            print(f"کاربر جدید اضافه شد: {cid}")
    if new_offset > offset:
        save_offset(new_offset)
    return chat_ids


def item_id(entry):
    raw = entry.get("id") or entry.get("link") or entry.get("title", "")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_relevant(entry):
    text = (entry.get("title", "") + " " + entry.get("summary", "")).lower()
    return any(kw.lower() in text for kw in KEYWORDS)


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


def apply_replacements(text, original_text):
    text = re.sub(r"(آیت\s*الله|امام)?\s*خامنه\s*ای", "خامنه‌ای", text)
    text = re.sub(r"(آیت\s*الله|امام)?\s*خمینی", "خمینی", text)
    text = text.replace("رهبر شهید", "جسد خامنه‌ای")
    text = text.replace("جمهوری اسلامی ایران", "جمهوری اسلامی")
    text = text.replace("رژیم صهیونیستی", "اسرائیل")
    text = text.replace("شهدای لبنان", "کشته‌شدگان لبنانی")
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


def detect_halo(text):
    has_iran = "ایران" in text
    has_war_word = "جنگ" in text
    turkey_migration = ("ترکیه" in text) and ("قانون" in text) and ("مهاجرت" in text)
    turkey_war = ("ترکیه" in text) and has_war_word
    if turkey_migration or turkey_war:
        return True, (255, 140, 0, 100)
    if has_iran and has_war_word and any(c in text for c in WAR_COUNTRIES):
        return True, (255, 40, 40, 100)
    return False, None


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


def make_marble_background(width, height):
    base = Image.new("RGB", (width, height), (10, 10, 10))
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    gold_tones = [(255, 215, 0), (212, 175, 55), (255, 230, 150)]
    vein_count = random.randint(14, 30)
    base_angle_bias = random.choice(["horizontal", "vertical", "diagonal"])
    for _ in range(vein_count):
        x, y = random.randint(0, width), random.randint(0, height)
        pts = [(x, y)]
        for _ in range(5):
            if base_angle_bias == "horizontal":
                x += random.randint(-220, 220)
                y += random.randint(20, 60)
            elif base_angle_bias == "vertical":
                x += random.randint(-40, 40)
                y += random.randint(60, 200)
            else:
                x += random.randint(-160, 160)
                y += random.randint(60, 180)
            pts.append((x, y))
        color = random.choice(gold_tones)
        alpha = random.randint(35, 110)
        draw.line(pts, fill=color + (alpha,), width=random.randint(1, 4))
    overlay = overlay.filter(ImageFilter.GaussianBlur(random.uniform(1.0, 2.2)))
    img = Image.alpha_composite(base.convert("RGBA"), overlay)

    shine = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shine)
    for _ in range(4):
        sx = random.randint(0, width)
        sy = random.randint(0, height)
        sr = random.randint(int(width * 0.15), int(width * 0.4))
        sd.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=(255, 255, 255, random.randint(10, 22)))
    shine = shine.filter(ImageFilter.GaussianBlur(120))
    img = Image.alpha_composite(img, shine).convert("RGB")
    return img


def draw_alert_icon(img, draw, x_center, y_center, halo_rgba):
    if halo_rgba:
        size = 220
        halo_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        hd = ImageDraw.Draw(halo_img)
        hd.ellipse([0, 0, size, size], fill=halo_rgba)
        halo_img = halo_img.filter(ImageFilter.GaussianBlur(30))
        img.paste(halo_img, (x_center - size // 2, y_center - size // 2), halo_img)
    r = 45
    draw.ellipse([x_center - r, y_center - r, x_center + r, y_center + r], fill=(220, 20, 20, 255))
    excl_font = load_font(FONT_BOLD, 55)
    tw = draw.textlength("!", font=excl_font)
    draw.text((x_center - tw / 2, y_center - 32), "!", font=excl_font, fill="white")


def draw_corner_sparkle(draw, width, height):
    corners = [(20, 20), (width - 20, 20), (20, height - 20), (width - 20, height - 20)]
    for cx, cy in corners:
        for r, alpha in [(14, 200), (24, 100), (34, 50)]:
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 240, 180, alpha), width=2)


def make_image(source_name, headline_fa, body_fa, important_topic, halo_color):
    source_name = clean_text(source_name)
    headline_fa = clean_text(headline_fa)
    body_fa = clean_text(body_fa)

    dummy = Image.new("RGB", (10, 10))
    d = ImageDraw.Draw(dummy)

    source_font = load_font(FONT_BOLD, 52)
    headline_font = load_font(FONT_BOLD, 46)
    body_font = load_font(FONT_REGULAR, 40)
    footer_font = load_font(FONT_BOLD, 42)
    insta_font = load_font(FONT_REGULAR, 32)

    max_w = IMG_WIDTH - 2 * PADDING
    headline_lines = wrap_text(headline_fa, headline_font, max_w, d)
    body_lines = wrap_text(body_fa, body_font, max_w, d) if body_fa else []

    top_area = BANNER_HEIGHT + 50 + len(headline_lines) * 62 + 25
    body_height = len(body_lines) * 60
    footer_height = 150
    total_height = max(top_area + body_height + footer_height, IMG_HEIGHT)

    img = make_marble_background(IMG_WIDTH, total_height).convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")

    draw.rectangle([0, 0, IMG_WIDTH, BANNER_HEIGHT], fill=(200, 16, 46, 255))
    shaped_src = shape_text(source_name)
    sw = draw.textlength(shaped_src, font=source_font)
    draw.text(((IMG_WIDTH - sw) / 2, BANNER_HEIGHT - 78), shaped_src, font=source_font, fill="white")

    y = BANNER_HEIGHT + 50
    for line in headline_lines:
        draw_center_line(draw, line, headline_font, y, (144, 238, 144, 255), (0, 0, 0, 255), IMG_WIDTH)
        y += 62

    y += 25
    for line in body_lines:
        draw_center_line(draw, line, body_font, y, (255, 255, 255, 255), (0, 0, 0, 255), IMG_WIDTH)
        y += 60

    shaped_footer = shape_text("خبر با نوید")
    fw = draw.textlength(shaped_footer, font=footer_font)
    draw.text(((IMG_WIDTH - fw) / 2, total_height - footer_height + 15), shaped_footer, font=footer_font, fill=(0, 150, 136, 255))

    insta_text = "Instagram : @NM_EST"
    iw = draw.textlength(insta_text, font=insta_font)
    draw.text(((IMG_WIDTH - iw) / 2, total_height - footer_height + 65), insta_text, font=insta_font, fill=(180, 180, 180, 255))

    if important_topic or halo_color:
        draw_alert_icon(img, draw, 100, BANNER_HEIGHT + 60, halo_color)

    draw_corner_sparkle(draw, IMG_WIDTH, total_height)

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
                resp = requests.post(url, data={"chat_id": cid, "caption": caption}, files={"photo": photo}, timeout=30)
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
    result = run_with_timeout(_do_fetch, (feed_url,), FEED_TIMEOUT + 5, default=None)
    if result is None:
        print(f"⛔ فید ناموفق: {feed_url}")
    elif not getattr(result, "entries", None):
        print(f"⚠️ فید خالی: {feed_url}")
    else:
        print(f"✅ فید موفق: {feed_url} -> {len(result.entries)} خبر")
    return result


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
            summary = clean_text(re.sub("<[^<]+?>", "", entry.get("summary", "")))[:SUMMARY_MAX_CHARS]
            original_full = f"{title}. {summary}"

            headline_fa = clean_text(translate_to_persian(title))
            body_fa = clean_text(translate_to_persian(summary)) if summary else ""

            headline_fa = apply_replacements(headline_fa, original_full)
            body_fa = apply_replacements(body_fa, original_full)

            full_check = original_full + " " + headline_fa + " " + body_fa
            important_topic = detect_important_topic(full_check)
            has_halo, halo_color = detect_halo(full_check)

            img_path = make_image(source_name, headline_fa, body_fa, important_topic or has_halo, halo_color)
            caption_text = f"{headline_fa}\n\n{body_fa}\n\nInstagram: @NM_EST" if body_fa else f"{headline_fa}\n\nInstagram: @NM_EST"
            if len(caption_text) > 1000:
                caption_text = caption_text[:1000] + "…"
            ok = send_photo_to_all(chat_ids, img_path, caption_text)
            if ok:
                sent_ids.add(eid)
                sent_count += 1
                save_json_set(SENT_IDS_FILE, sent_ids)
                print(f"ارسال شد: {source_name} -> {title[:50]}")
            else:
                print(f"⚠️ ارسال ناموفق برای: {source_name} -> {title[:50]}")
            time.sleep(2)
    return sent_ids


def main():
    print(f"شروع اجرا در {datetime.now()}")
    if not BOT_TOKEN:
        print("لطفاً TELEGRAM_BOT_TOKEN را تنظیم کنید.")
        return
    chat_ids = load_json_set(CHAT_IDS_FILE, [OWNER_CHAT_ID])
    if OWNER_CHAT_ID:
        chat_ids.add(str(OWNER_CHAT_ID))
    print(f"تعداد کاربران فعلی: {len(chat_ids)} -> {chat_ids}")
    sent_ids = load_json_set(SENT_IDS_FILE, [])
    start = time.time()
    hard_deadline = start + RUN_DURATION_SECONDS
    while time.time() - start < RUN_DURATION_SECONDS:
        chat_ids = poll_new_starters(chat_ids)
        if OWNER_CHAT_ID:
            chat_ids.add(str(OWNER_CHAT_ID))
        save_json_set(CHAT_IDS_FILE, chat_ids)
        sent_ids = fetch_and_process(sent_ids, chat_ids, hard_deadline)
        print(f"⏳ یک دور کامل تمام شد، {int(hard_deadline - time.time())} ثانیه باقی مانده")
        time.sleep(CHECK_INTERVAL_SECONDS)
    print("پایان اجرا.")


if __name__ == "__main__":
    main()
