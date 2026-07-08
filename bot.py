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

            body_fa = dedupe_sentences(body_fa)
            body_fa = strip_leading_headline_from_body(headline_fa, body_fa)

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
