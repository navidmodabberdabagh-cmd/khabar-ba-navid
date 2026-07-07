# -*- coding: utf-8 -*-
RSS_FEEDS = {
    "Fox News": "https://moxie.foxnews.com/google-publisher/latest.xml",
    "Fox News World": "https://moxie.foxnews.com/google-publisher/world.xml",
    "DW English": "https://rss.dw.com/rdf/rss-en-all",
    "ایران اینترنشنال": "https://www.iranintl.com/fa/rss",
    "CNBC": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "France24": "https://www.france24.com/en/rss",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "ایسنا": "https://www.isna.ir/rss",
    "ایرنا": "https://www.irna.ir/rss",
    "یورونیوز فارسی": "https://parsi.euronews.com/rss",
    "العربیه فارسی": "https://farsi.alarabiya.net/rss.xml",
    "Al Arabiya": "https://english.alarabiya.net/tools/rss",
    "Arab News": "https://www.arabnews.com/rss.xml",
    "Gulf News": "https://gulfnews.com/rss",
    "Times of Israel": "https://www.timesofisrael.com/feed/",
    "Jerusalem Post": "https://www.jpost.com/rss/rssfeedsfrontpage.aspx",
    "Haaretz": "https://www.haaretz.com/cmlink/1.628752",
    "Daily Sabah": "https://www.dailysabah.com/rssFeed/10000",
    "Hürriyet": "https://www.hurriyet.com.tr/rss/anasayfa",
    "Anadolu Agency": "https://www.aa.com.tr/en/rss/default?cat=live",
    "RFI": "https://www.rfi.fr/en/rss",
    "AP News": "https://apnews.com/rss",
    "Reuters": "https://www.reutersagency.com/feed/?best-topics=middle-east",
    "CBC": "https://www.cbc.ca/cmlink/rss-world",
    "News24": "https://www.news24.com/rss",
    "Nikkei Asia": "https://asia.nikkei.com/rss/feed/nar",
    "South China Morning Post": "https://www.scmp.com/rss/91/feed",
    "ABC News Australia": "https://www.abc.net.au/news/feed/51120/rss.xml",
    "Science Daily": "https://www.sciencedaily.com/rss/health_medicine.xml",
    "Medical Xpress": "https://medicalxpress.com/rss-feed/",
    "BBC Sport Football": "https://feeds.bbci.co.uk/sport/football/rss.xml",
    "EU Home Affairs": "https://home-affairs.ec.europa.eu/rss_en",
    "GOV UK Home Office": "https://www.gov.uk/government/organisations/home-office.atom",
}

KEYWORDS = [
    "iran", "ایران", "tehran", "تهران", "trump", "ترامپ",
    "hezbollah", "حزب الله", "israel", "اسرائیل",
    "iraq", "عراق", "pakistan", "پاکستان", "afghanistan", "افغانستان",
    "azerbaijan", "آذربایجان", "armenia", "ارمنستان", "russia", "روسیه",
    "ukraine", "اوکراین", "اکراین", "greece", "یونان", "turkey", "ترکیه",
    "persian gulf", "خلیج فارس", "uae", "امارات", "saudi", "عربستان",
    "qatar", "قطر", "kuwait", "کویت", "bahrain", "بحرین", "oman", "عمان",
    "china", "چین", "iran football", "فوتبال ایران", "iran economy", "اقتصاد ایران",
    "iran sanctions", "تحریم ایران", "migration", "مهاجرت",
    "رضا پهلوی", "pahlavi",
    "بورس", "stock market", "oil price", "نفت برنت", "borsa",
    "cancer treatment", "درمان سرطان", "cancer cure", "immunotherapy",
    "desalination", "آب شیرین‌سازی", "water technology",
    "world cup", "جام جهانی", "gulf cup", "لیگ خلیج فارس", "team melli", "football", "فوتبال",
    "visa", "ویزا", "residence permit", "اقامت", "immigration law", "قانون مهاجرت",
    "asylum", "پناهندگی", "deportation", "اخراج مهاجران",
    # آب و هوا فقط با این کلمات + شهر مجاز match می‌شود (فیلتر جداگانه در bot.py)
    "weather", "storm", "flood", "snow", "rain", "tsunami",
]

# فقط این شهرها/استان‌ها برای اخبار آب‌وهوا مجازند
WEATHER_ALLOWED_LOCATIONS = [
    "استانبول", "آنتالیا", "تهران", "آذربایجان شرقی", "آذربایجان غربی",
    "اصفهان", "خراسان رضوی", "مشهد", "فارس", "شیراز", "گیلان", "مازندران",
    "آبادان", "هرمزگان", "کیش", "بوشهر", "یزد", "کرمان",
    "سیستان و بلوچستان", "زاهدان", "چابهار",
]

WEATHER_SEVERITY_WORDS = [
    "باران شدید", "بارش شدید", "برف سنگین", "سیل", "سیلاب", "سونامی",
    "هشدار قرمز", "هشدار زرد", "طوفان", "heavy rain", "heavy snow",
    "flood", "tsunami", "storm warning",
]

MEDICAL_SOURCES = {"Science Daily", "Medical Xpress"}
