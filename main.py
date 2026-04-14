import telebot
from telebot import types
import sqlite3
import requests
import json
import random
import datetime
import time
import threading
import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

# ══════════════════════════════════════════════════
#                   الإعدادات الأساسية
# ══════════════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN") or "8689991409:AAEm8BUr5PTUq14NaL0PjhWk91svZRGR0cc"
ADMIN_ID   = int(os.environ.get("ADMIN_ID") or 7586128651)
CHANNEL_USERNAME = "@mviicxr7"
CHANNEL_LINK     = "https://t.me/mviicxr7"

# ✅ مسار قاعدة بيانات دائم (ينصح باستخدامه في بيئات الاستضافة)
DEFAULT_DB_PATH = "/app/data/islamic_bot.db"   # مناسب لـ Docker/Koyeb/Railway
DB_PATH = os.environ.get("DB_PATH") or DEFAULT_DB_PATH

# 🛠️ إنشاء المجلد الأب إذا لم يكن موجوداً
db_dir = os.path.dirname(DB_PATH)
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir, exist_ok=True)

bot       = telebot.TeleBot(BOT_TOKEN, parse_mode=None)
scheduler = BackgroundScheduler(timezone="Africa/Cairo")

# ══════════════════════════════════════════════════
#                   قاعدة البيانات
# ══════════════════════════════════════════════════

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            first_name  TEXT,
            last_name   TEXT,
            joined_at   TEXT,
            last_active TEXT,
            is_blocked  INTEGER DEFAULT 0
        )""")

    c.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id          INTEGER,
            channel_id       TEXT,
            channel_title    TEXT,
            channel_username TEXT,
            added_at         TEXT,
            UNIQUE(user_id, channel_id)
        )""")

    c.execute("""
        CREATE TABLE IF NOT EXISTS channel_settings (
            channel_id          TEXT PRIMARY KEY,
            user_id             INTEGER,
            is_active           INTEGER DEFAULT 0,
            interval_hours      INTEGER DEFAULT 6,
            post_quran          INTEGER DEFAULT 1,
            post_hadith         INTEGER DEFAULT 1,
            post_adhkar         INTEGER DEFAULT 1,
            post_morning        INTEGER DEFAULT 0,
            morning_time        TEXT    DEFAULT '06:00',
            post_evening        INTEGER DEFAULT 0,
            evening_time        TEXT    DEFAULT '17:00',
            post_sleep          INTEGER DEFAULT 0,
            sleep_time          TEXT    DEFAULT '22:00',
            use_emoji           INTEGER DEFAULT 1,
            format_style        TEXT    DEFAULT 'fancy',
            last_post_time      TEXT
        )""")

    c.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER,
            content_type TEXT,
            content      TEXT,
            saved_at     TEXT
        )""")

    c.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id         INTEGER PRIMARY KEY,
            daily_reminder  INTEGER DEFAULT 0,
            reminder_time   TEXT    DEFAULT '08:00',
            night_mode      INTEGER DEFAULT 0
        )""")

    conn.commit()
    conn.close()


def db():
    return sqlite3.connect(DB_PATH)


def register_user(user):
    conn = db()
    c    = conn.cursor()
    now  = _now()
    c.execute("""
        INSERT OR IGNORE INTO users
            (user_id, username, first_name, last_name, joined_at, last_active)
        VALUES (?,?,?,?,?,?)""",
        (user.id, user.username, user.first_name, user.last_name, now, now))
    c.execute("""
        UPDATE users SET last_active=?, username=?, first_name=?
        WHERE user_id=?""",
        (now, user.username, user.first_name, user.id))
    c.execute("INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (user.id,))
    conn.commit()
    conn.close()


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ══════════════════════════════════════════════════
#                 تحميل البيانات
# ══════════════════════════════════════════════════

# ── أحاديث بخارية ──────────────────────────────
hadith_list = []

def load_hadiths():
    global hadith_list
    urls = [
        "https://raw.githubusercontent.com/fawazahmed0/hadith-api/main/editions/ara-bukhari.json",
        "https://raw.githubusercontent.com/fawazahmed0/hadith-api/main/editions/eng-bukhari.json",
    ]
    for url in urls:
        try:
            r = requests.get(url, timeout=15)
            d = r.json()
            if isinstance(d, dict) and "hadiths" in d:
                hadith_list = d["hadiths"]
            elif isinstance(d, list):
                hadith_list = d
            if hadith_list:
                print(f"✅ تم تحميل {len(hadith_list)} حديث")
                return
        except Exception as e:
            print(f"⚠️  خطأ تحميل الأحاديث ({url[:40]}…): {e}")

    # بيانات احتياطية
    hadith_list = [
        {"hadithnumber": 1,  "chapter": "بدء الوحي",
         "hadith": "إِنَّمَا الأَعْمَالُ بِالنِّيَّاتِ، وَإِنَّمَا لِكُلِّ امْرِئٍ مَا نَوَى."},
        {"hadithnumber": 8,  "chapter": "الإيمان",
         "hadith": "الإِسْلاَمُ أَنْ تَشْهَدَ أَنْ لاَ إِلَهَ إِلاَّ اللَّهُ وَأَنَّ مُحَمَّدًا رَسُولُ اللَّهِ."},
        {"hadithnumber": 52, "chapter": "الإيمان",
         "hadith": "الحَلاَلُ بَيِّنٌ، وَالحَرَامُ بَيِّنٌ، وَبَيْنَهُمَا مُشَبَّهَاتٌ لاَ يَعْلَمُهَا كَثِيرٌ مِنَ النَّاسِ."},
    ]
    print("⚠️  تم استخدام الأحاديث الاحتياطية")


# ── أذكار ─────────────────────────────────────
adhkar_morning = []
adhkar_evening = []
adhkar_sleep   = []
adhkar_misc    = []

_FALLBACK_MORNING = [
    {"content": "اللَّهُمَّ بِكَ أَصْبَحْنَا، وَبِكَ أَمْسَيْنَا، وَبِكَ نَحْيَا، وَبِكَ نَمُوتُ، وَإِلَيْكَ النُّشُورُ.", "count": 1},
    {"content": "أَصْبَحْنَا عَلَى فِطْرَةِ الإِسْلاَمِ، وَعَلَى كَلِمَةِ الإِخْلاَصِ، وَعَلَى دِينِ نَبِيِّنَا مُحَمَّدٍ ﷺ.", "count": 1},
    {"content": "اللَّهُمَّ أَنْتَ رَبِّي لاَ إِلَهَ إِلاَّ أَنْتَ، خَلَقْتَنِي وَأَنَا عَبْدُكَ.", "count": 1},
    {"content": "سُبْحَانَ اللَّهِ وَبِحَمْدِهِ.", "count": 100},
]
_FALLBACK_EVENING = [
    {"content": "اللَّهُمَّ بِكَ أَمْسَيْنَا، وَبِكَ أَصْبَحْنَا، وَبِكَ نَحْيَا، وَبِكَ نَمُوتُ، وَإِلَيْكَ الْمَصِيرُ.", "count": 1},
    {"content": "أَعُوذُ بِكَلِمَاتِ اللَّهِ التَّامَّاتِ مِنْ شَرِّ مَا خَلَقَ.", "count": 3},
    {"content": "اللَّهُمَّ عَافِنِي فِي بَدَنِي، اللَّهُمَّ عَافِنِي فِي سَمْعِي، اللَّهُمَّ عَافِنِي فِي بَصَرِي.", "count": 3},
]
_FALLBACK_SLEEP = [
    {"content": "بِاسْمِكَ اللَّهُمَّ أَمُوتُ وَأَحْيَا.", "count": 1},
    {"content": "اللَّهُمَّ قِنِي عَذَابَكَ يَوْمَ تَبْعَثُ عِبَادَكَ.", "count": 3},
    {"content": "سُبْحَانَ اللَّهِ (٣٣)، الْحَمْدُ لِلَّهِ (٣٣)، اللَّهُ أَكْبَرُ (٣٤).", "count": 1},
]
_FALLBACK_MISC = [
    {"content": "لَا إِلَهَ إِلَّا اللَّهُ وَحْدَهُ لَا شَرِيكَ لَهُ، لَهُ الْمُلْكُ وَلَهُ الْحَمْدُ وَهُوَ عَلَى كُلِّ شَيْءٍ قَدِيرٌ.", "count": 100},
    {"content": "سُبْحَانَ اللَّهِ وَبِحَمْدِهِ، سُبْحَانَ اللَّهِ الْعَظِيمِ.", "count": 1},
    {"content": "اللَّهُمَّ صَلِّ عَلَى مُحَمَّدٍ وَعَلَى آلِ مُحَمَّدٍ.", "count": 10},
    {"content": "رَبِّ اغْفِرْ لِي وَتُبْ عَلَيَّ، إِنَّكَ أَنْتَ التَّوَّابُ الرَّحِيمُ.", "count": 100},
]


def load_adhkar():
    global adhkar_morning, adhkar_evening, adhkar_sleep, adhkar_misc
    try:
        url = "https://raw.githubusercontent.com/rn0x/Adhkar-json/main/adhkar.json"
        r = requests.get(url, timeout=15)
        data = r.json()

        for item in data:
            cat = item.get("category", "").lower()
            if "صباح" in cat:
                adhkar_morning.append(item)
            elif "مساء" in cat:
                adhkar_evening.append(item)
            elif "نوم" in cat or "منام" in cat:
                adhkar_sleep.append(item)
            else:
                adhkar_misc.append(item)

        print(f"✅ أذكار: صباح={len(adhkar_morning)} مساء={len(adhkar_evening)} "
              f"نوم={len(adhkar_sleep)} أخرى={len(adhkar_misc)}")
    except Exception as e:
        print(f"⚠️  خطأ تحميل الأذكار: {e}")

    # fallback
    if not adhkar_morning: adhkar_morning = _FALLBACK_MORNING
    if not adhkar_evening: adhkar_evening = _FALLBACK_EVENING
    if not adhkar_sleep:   adhkar_sleep   = _FALLBACK_SLEEP
    if not adhkar_misc:    adhkar_misc    = _FALLBACK_MISC


# ══════════════════════════════════════════════════
#                 دوال الـ API
# ══════════════════════════════════════════════════

def get_random_ayah():
    try:
        # جلب قائمة السور
        r = requests.get("https://api.alquran.cloud/v1/surah", timeout=10)
        data = r.json()

        if data.get("code") != 200:
            return None

        surahs = data["data"]

        # اختيار سورة عشوائية
        surah = random.choice(surahs)
        surah_num = surah["number"]

        # عدد الآيات في السورة
        total_ayahs = surah["numberOfAyahs"]

        # اختيار آية عشوائية
        ayah_num = random.randint(1, total_ayahs)

        # جلب الآية
        r2 = requests.get(
            f"https://api.alquran.cloud/v1/ayah/{surah_num}:{ayah_num}",
            timeout=10
        )
        d2 = r2.json()

        if d2.get("code") == 200:
            a = d2["data"]
            return {
                "text": a["text"],
                "surah_name": a["surah"]["name"],
                "surah_number": surah_num,
                "number_in_surah": a["numberInSurah"],
                "juz": a["juz"],
            }

    except Exception as e:
        print(f"⚠️ خطأ جلب الآية: {e}")

    return None


def get_ayah_by_surah(surah_num):
    """جلب آية عشوائية من سورة محددة."""
    try:
        r = requests.get(f"https://api.alquran.cloud/v1/surah/{surah_num}", timeout=10)
        d = r.json()
        if d.get("code") == 200:
            count = d["data"]["numberOfAyahs"]
            ayah_num = random.randint(1, count)
            r2 = requests.get(
                f"https://api.alquran.cloud/v1/ayah/{surah_num}:{ayah_num}", timeout=10)
            d2 = r2.json()
            if d2.get("code") == 200:
                a = d2["data"]
                return {
                    "text":            a["text"],
                    "surah_name":      a["surah"]["name"],
                    "surah_number":    surah_num,
                    "number_in_surah": a["numberInSurah"],
                    "juz":             a["juz"],
                }
    except Exception as e:
        print(f"⚠️  خطأ جلب آية السورة: {e}")
    return None


def get_random_hadith():
    if not hadith_list:
        return None
    return random.choice(hadith_list)


def get_adhkar(category):
    pool = {
        "morning": adhkar_morning,
        "evening": adhkar_evening,
        "sleep":   adhkar_sleep,
        "misc":    adhkar_misc,
    }.get(category, adhkar_misc)
    if not pool:
        return None
    item = random.choice(pool)
    return item


# ══════════════════════════════════════════════════
#                  تنسيق الرسائل
# ══════════════════════════════════════════════════

_CAT_AR = {
    "morning": "أذكار الصباح",
    "evening": "أذكار المساء",
    "sleep":   "أذكار النوم",
    "misc":    "أدعية وأذكار متنوعة",
}
_CAT_ICON = {
    "morning": "🌅",
    "evening": "🌇",
    "sleep":   "🌙",
    "misc":    "🤲",
}


def fmt_ayah(ayah, emoji=True, style="fancy"):
    if not ayah:
        return "❌ تعذّر جلب الآية، حاول مجدداً."
    if style == "fancy":
        header = "📖 *آية كريمة*\n═══════════════\n\n" if emoji else ""
        footer = (f"\n\n📌 سورة *{ayah['surah_name']}* • الآية {ayah['number_in_surah']}"
                  f"\n📚 الجزء: {ayah['juz']}") if emoji else \
                 (f"\n\n— سورة {ayah['surah_name']} ({ayah['number_in_surah']})")
    else:
        header = ""
        footer = f"\n— سورة {ayah['surah_name']} ({ayah['number_in_surah']})"

    return f"{header}﴿ {ayah['text']} ﴾{footer}"


def fmt_hadith(hadith, emoji=True, style="fancy"):
    if not hadith:
        return "❌ تعذّر جلب الحديث، حاول مجدداً."
    text    = hadith.get("hadith") or hadith.get("text") or hadith.get("body") or "—"
    number  = hadith.get("hadithnumber") or hadith.get("id") or ""
    chapter = hadith.get("chapter") or hadith.get("sectiondesc") or ""

    if style == "fancy":
        header = "📜 *حديث شريف*\n═══════════════\n\n" if emoji else ""
        footer = f"\n\n📚 *صحيح البخاري* رقم {number}" if emoji else f"\n— البخاري ({number})"
        if chapter:
            footer += f"\n📌 {chapter}"
    else:
        header = ""
        footer = f"\n— البخاري ({number})"

    return f"{header}{text}{footer}"


def fmt_adhkar(item, category="misc", emoji=True, style="fancy"):
    if not item:
        return "❌ تعذّر جلب الذكر، حاول مجدداً."

    icon  = _CAT_ICON.get(category, "📿")
    title = _CAT_AR.get(category, "أذكار")

    # ── استخراج عنوان الذكر من API ──
    api_title = ""
    if isinstance(item, dict):
        api_title = item.get("category") or item.get("title") or ""

    texts = []
    counts = []

    # ── استخراج الأذكار ──
    if isinstance(item, dict) and "array" in item:

        arr = item["array"]

        if isinstance(arr, list):
            for x in arr:
                if isinstance(x, dict):
                    txt = x.get("text")
                    if txt:
                        texts.append(txt.strip())
                        counts.append(x.get("count", 1))

        elif isinstance(arr, dict):
            txt = arr.get("text")
            if txt:
                texts.append(txt.strip())
                counts.append(arr.get("count", 1))

    else:
        txt = item.get("content") or item.get("text")
        if txt:
            texts.append(txt.strip())
            counts.append(item.get("count", 1))

    if not texts:
        texts = [str(item)]

    # ── بناء الرسالة ──
    msg = ""

    if style == "fancy":
        msg += f"{icon} *{title}*\n"
        msg += "━━━━━━━━━━━━━━━\n\n"

        # ⭐ إضافة العنوان من API
        if api_title:
            msg += f"📌 {api_title}\n\n"

    for i, t in enumerate(texts):
        t = t.replace("((", "").replace("))", "").strip()
        msg += f"🕋 {t}\n"

        if i < len(counts) and counts[i] and int(counts[i]) > 1:
            msg += f"🔄 {counts[i]} مرات\n"

        msg += "\n"

    return msg.strip()
# ══════════════════════════════════════════════════
#                   الأزرار (Keyboards)
# ══════════════════════════════════════════════════

def kb_main():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    m.add(
        types.KeyboardButton("📖 القرآن الكريم"),
        types.KeyboardButton("📜 الأحاديث"),
        types.KeyboardButton("📿 الأذكار"),
        types.KeyboardButton("⚙️ إعدادات قناتي"),
        types.KeyboardButton("⭐ المفضلة"),
        types.KeyboardButton("🔔 التذكير اليومي"),
        types.KeyboardButton("ℹ️ معلومات"),
    )
    return m


def kb_main_admin():
    m = kb_main()
    m.add(types.KeyboardButton("👑 لوحة الإدارة"))
    return m


def kb_subscribe():
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("📢 اشترك في القناة", url=CHANNEL_LINK))
    m.add(types.InlineKeyboardButton("🔄 تحقق من الاشتراك", callback_data="check_sub"))
    return m


def kb_back_main():
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_main"))
    return m


def kb_quran():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton("🔁 آية أخرى",    callback_data="rnd_ayah"),
        types.InlineKeyboardButton("⭐ حفظ",          callback_data="save_ayah"),
    )
    m.add(types.InlineKeyboardButton("🔍 بحث عن سورة", callback_data="search_surah"))
    m.add(types.InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_main"))
    return m


def kb_hadith():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton("🔁 حديث آخر",  callback_data="rnd_hadith"),
        types.InlineKeyboardButton("⭐ حفظ",        callback_data="save_hadith"),
    )
    m.add(types.InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_main"))
    return m


def kb_adhkar_menu():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton("🌅 أذكار الصباح",  callback_data="adhkar_morning"),
        types.InlineKeyboardButton("🌇 أذكار المساء",  callback_data="adhkar_evening"),
        types.InlineKeyboardButton("🌙 أذكار النوم",   callback_data="adhkar_sleep"),
        types.InlineKeyboardButton("🤲 أدعية متنوعة", callback_data="adhkar_misc"),
    )
    m.add(types.InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_main"))
    return m


def kb_adhkar_item(cat):
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton("🔁 ذكر آخر",  callback_data=f"adhkar_{cat}"),
        types.InlineKeyboardButton("⭐ حفظ",       callback_data=f"save_adhkar_{cat}"),
    )
    m.add(types.InlineKeyboardButton("🔙 قائمة الأذكار", callback_data="adhkar_menu"))
    return m


def kb_channels(user_id):
    m = types.InlineKeyboardMarkup()
    conn = db()
    rows = conn.execute(
        "SELECT channel_id, channel_title FROM channels WHERE user_id=?", (user_id,)
    ).fetchall()
    conn.close()
    for cid, title in rows:
        m.add(types.InlineKeyboardButton(f"📡 {title}", callback_data=f"ch_cfg_{cid}"))
    m.add(types.InlineKeyboardButton("➕ إضافة قناة جديدة", callback_data="add_channel"))
    m.add(types.InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_main"))
    return m


def _get_cs(channel_id):
    conn = db()
    row  = conn.execute(
        "SELECT * FROM channel_settings WHERE channel_id=?", (channel_id,)
    ).fetchone()
    conn.close()
    return row   # returns tuple


def kb_ch_settings(channel_id):
    row = _get_cs(channel_id)
    if not row:
        return None
    # indices: 0=channel_id 1=user_id 2=is_active 3=interval 4=post_quran
    #          5=post_hadith 6=post_adhkar 7=post_morning 8=morning_time
    #          9=post_evening 10=evening_time 11=post_sleep 12=sleep_time
    #          13=use_emoji 14=format_style 15=last_post_time
    is_active = row[2];  interval = row[3]
    pq = row[4]; ph = row[5]; pa = row[6]
    pm = row[7]; pe = row[9]; ps = row[11]
    emoji_on = row[13]

    ck  = lambda v: "✅" if v else "❌"
    m   = types.InlineKeyboardMarkup(row_width=1)

    lbl = "⏸ إيقاف النشر" if is_active else "▶️ بدء النشر"
    m.add(types.InlineKeyboardButton(lbl, callback_data=f"tg_active_{channel_id}"))

    m.add(types.InlineKeyboardButton(
        f"⏱ الفاصل الزمني: كل {interval} ساعة", callback_data=f"set_interval_{channel_id}"))

    m.row(
        types.InlineKeyboardButton(f"{ck(pq)} 📖 القرآن",   callback_data=f"tg_q_{channel_id}"),
        types.InlineKeyboardButton(f"{ck(ph)} 📜 الحديث",   callback_data=f"tg_h_{channel_id}"),
    )
    m.add(types.InlineKeyboardButton(
        f"{ck(pa)} 📿 الأذكار العامة", callback_data=f"tg_a_{channel_id}"))

    m.add(types.InlineKeyboardButton("─── أذكار مجدولة ───", callback_data="noop"))
    m.row(
        types.InlineKeyboardButton(f"{ck(pm)} 🌅 الصباح",  callback_data=f"tg_m_{channel_id}"),
        types.InlineKeyboardButton(f"{ck(pe)} 🌇 المساء",  callback_data=f"tg_e_{channel_id}"),
    )
    m.add(types.InlineKeyboardButton(
        f"{ck(ps)} 🌙 النوم", callback_data=f"tg_s_{channel_id}"))

    m.add(types.InlineKeyboardButton(
        f"{ck(emoji_on)} إيموجي",  callback_data=f"tg_em_{channel_id}"))

    m.add(types.InlineKeyboardButton("🗑 حذف القناة",          callback_data=f"del_ch_{channel_id}"))
    m.add(types.InlineKeyboardButton("🔙 قائمة القنوات",        callback_data="show_channels"))
    return m


def kb_interval(channel_id):
    m = types.InlineKeyboardMarkup(row_width=3)
    for h in [1, 3, 6, 12, 24]:
        m.add(types.InlineKeyboardButton(
            f"كل {h} ساعة", callback_data=f"int_{h}_{channel_id}"))
    m.add(types.InlineKeyboardButton("🔙 رجوع", callback_data=f"ch_cfg_{channel_id}"))
    return m


def kb_admin():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton("👥 المستخدمون",         callback_data="adm_users"),
        types.InlineKeyboardButton("📡 القنوات",            callback_data="adm_channels"),
    )
    m.add(
        types.InlineKeyboardButton("📢 رسالة جماعية",       callback_data="adm_broadcast"),
        types.InlineKeyboardButton("🏆 أنشط المستخدمين",    callback_data="adm_top"),
    )
    m.add(types.InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_main"))
    return m


def kb_favorites(user_id, offset=0):
    conn = db()
    rows  = conn.execute(
        "SELECT id, content_type, content FROM favorites WHERE user_id=? LIMIT 5 OFFSET ?",
        (user_id, offset)
    ).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) FROM favorites WHERE user_id=?", (user_id,)
    ).fetchone()[0]
    conn.close()

    m = types.InlineKeyboardMarkup()
    icons = {"ayah": "📖", "hadith": "📜", "adhkar": "📿"}
    for fid, ftype, content in rows:
        preview = content[:35] + "…" if len(content) > 35 else content
        lbl = f"{icons.get(ftype, '⭐')} {preview}"
        m.add(types.InlineKeyboardButton(lbl, callback_data=f"vfav_{fid}"))

    nav = []
    if offset > 0:
        nav.append(types.InlineKeyboardButton("◀️", callback_data=f"fav_p_{offset - 5}"))
    if offset + 5 < total:
        nav.append(types.InlineKeyboardButton("▶️", callback_data=f"fav_n_{offset + 5}"))
    if nav:
        m.row(*nav)

    m.add(types.InlineKeyboardButton("🗑 مسح الكل",              callback_data="clear_favs"))
    m.add(types.InlineKeyboardButton("🔙 القائمة الرئيسية",      callback_data="back_main"))
    return m, total


def kb_reminder(user_id):
    conn = db()
    row  = conn.execute(
        "SELECT daily_reminder, reminder_time, night_mode FROM user_settings WHERE user_id=?",
        (user_id,)
    ).fetchone()
    conn.close()
    daily, rtime, night = row if row else (0, "08:00", 0)

    ck = lambda v: "✅" if v else "❌"
    m  = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton(
        f"{ck(daily)} التذكير اليومي", callback_data="tg_reminder"))
    m.add(types.InlineKeyboardButton(
        f"⏰ الوقت: {rtime}", callback_data="set_reminder_time"))
    m.add(types.InlineKeyboardButton(
        f"{ck(night)} 🌙 الوضع الليلي", callback_data="tg_nightmode"))
    m.add(types.InlineKeyboardButton(
        "🔙 القائمة الرئيسية", callback_data="back_main"))
    return m


# ══════════════════════════════════════════════════
#             التحقق من الاشتراك
# ══════════════════════════════════════════════════

def is_subscribed(user_id):
    try:
        m = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return m.status in ("member", "administrator", "creator")
    except Exception as e:
        print(f"⚠️  فحص الاشتراك: {e}")
        return False


def demand_subscription(chat_id):
    bot.send_message(
        chat_id,
        "🔐 *مرحباً بك في البوت الإسلامي!* 🌙\n\n"
        "للاستخدام يجب الاشتراك في قناتنا أولاً.\n"
        "اشترك ثم اضغط *تحقق من الاشتراك*:",
        parse_mode="Markdown",
        reply_markup=kb_subscribe(),
    )


# ══════════════════════════════════════════════════
#               إدارة حالة المستخدم
# ══════════════════════════════════════════════════
_states: dict = {}   # {user_id: {"state": str, "data": dict}}


def set_state(uid, state, data=None):
    _states[uid] = {"state": state, "data": data or {}}


def get_state(uid):
    return _states.get(uid, {"state": None, "data": {}})


def clear_state(uid):
    _states.pop(uid, None)


# ══════════════════════════════════════════════════
#            مؤقتات المستخدم الأخير (anti-spam)
# ══════════════════════════════════════════════════
_last_action: dict = {}

def throttle(uid, seconds=2):
    now = time.time()
    if now - _last_action.get(uid, 0) < seconds:
        return False
    _last_action[uid] = now
    return True


# ══════════════════════════════════════════════════
#              دوال المساعدة
# ══════════════════════════════════════════════════

def greet():
    h = datetime.datetime.now().hour
    if 5  <= h < 12: return "صباح الخير"
    if 12 <= h < 17: return "مرحباً"
    if 17 <= h < 21: return "مساء الخير"
    return "مساء النور"


def save_fav(user_id, ftype, content):
    conn = db()
    c    = conn.cursor()
    cnt  = c.execute(
        "SELECT COUNT(*) FROM favorites WHERE user_id=?", (user_id,)
    ).fetchone()[0]
    if cnt >= 50:
        c.execute("""DELETE FROM favorites WHERE id =
            (SELECT id FROM favorites WHERE user_id=? ORDER BY saved_at ASC LIMIT 1)""",
            (user_id,))
    c.execute(
        "INSERT INTO favorites (user_id, content_type, content, saved_at) VALUES (?,?,?,?)",
        (user_id, ftype, content, _now()))
    conn.commit()
    conn.close()


def toggle_col(channel_id, col):
    """Toggle 0/1 column in channel_settings. Returns new value."""
    conn = db()
    c    = conn.cursor()
    cur  = c.execute(
        f"SELECT {col} FROM channel_settings WHERE channel_id=?", (channel_id,)
    ).fetchone()
    new  = 0 if (cur and cur[0]) else 1
    c.execute(f"UPDATE channel_settings SET {col}=? WHERE channel_id=?", (new, channel_id))
    conn.commit()
    conn.close()
    return new


def owns_channel(user_id, channel_id):
    conn = db()
    row  = conn.execute(
        "SELECT id FROM channels WHERE channel_id=? AND user_id=?", (channel_id, user_id)
    ).fetchone()
    conn.close()
    return bool(row) or user_id == ADMIN_ID


def ch_settings_msg(channel_id):
    conn = db()
    row  = conn.execute(
        "SELECT channel_title FROM channels WHERE channel_id=?", (channel_id,)
    ).fetchone()
    cs   = conn.execute(
        "SELECT is_active, last_post_time FROM channel_settings WHERE channel_id=?", (channel_id,)
    ).fetchone()
    conn.close()
    title = row[0] if row else channel_id
    stat  = "✅ نشط" if (cs and cs[0]) else "⏸ متوقف"
    last  = cs[1] if (cs and cs[1]) else "لم ينشر بعد"
    return (
        f"⚙️ *إعدادات القناة*\n\n"
        f"📡 *{title}*\n"
        f"الحالة: {stat}\n"
        f"آخر نشر: {last}\n\n"
        f"اختر إعداداً:"
    )


# ══════════════════════════════════════════════════
#              نظام الجدولة (Scheduler)
# ══════════════════════════════════════════════════

def _post_content(channel_id):
    cs = _get_cs(channel_id)
    if not cs or not cs[2]:   # is_active
        return
    pool = []
    if cs[4]: pool.append("quran")
    if cs[5]: pool.append("hadith")
    if cs[6]: pool.append("adhkar")
    if not pool:
        return
    choice = random.choice(pool)
    emoji_on = bool(cs[13])
    style    = cs[14] or "fancy"
    try:
        if choice == "quran":
            msg = fmt_ayah(get_random_ayah(), emoji=emoji_on, style=style)
        elif choice == "hadith":
            msg = fmt_hadith(get_random_hadith(), emoji=emoji_on, style=style)
        else:
            msg = fmt_adhkar(get_adhkar("misc"), "misc", emoji=emoji_on, style=style)
        bot.send_message(channel_id, msg, parse_mode="Markdown")
        conn = db()
        conn.execute(
            "UPDATE channel_settings SET last_post_time=? WHERE channel_id=?",
            (_now(), channel_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️  نشر القناة {channel_id}: {e}")


def _post_adhkar_job(channel_id, adhkar_type):
    cs = _get_cs(channel_id)
    if not cs:
        return
    col_map = {"morning": 7, "evening": 9, "sleep": 11}
    if not cs[col_map[adhkar_type]]:
        return
    emoji_on = bool(cs[13]); style = cs[14] or "fancy"
    try:
        msg = fmt_adhkar(get_adhkar(adhkar_type), adhkar_type, emoji=emoji_on, style=style)
        bot.send_message(channel_id, msg, parse_mode="Markdown")
    except Exception as e:
        print(f"⚠️  أذكار {adhkar_type} للقناة {channel_id}: {e}")


def _daily_reminders():
    now = datetime.datetime.now().strftime("%H:%M")
    conn = db()
    rows = conn.execute(
        "SELECT user_id, reminder_time FROM user_settings WHERE daily_reminder=1"
    ).fetchall()
    conn.close()
    for uid, rtime in rows:
        if rtime and rtime[:5] == now:
            try:
                msg = "🌟 *تذكيرك اليومي*\n\n" + fmt_ayah(get_random_ayah())
                bot.send_message(uid, msg, parse_mode="Markdown")
            except:
                pass


def activate_channel_scheduler(channel_id, hours):
    jid = f"ch_{channel_id}"
    if scheduler.get_job(jid):
        scheduler.remove_job(jid)
    scheduler.add_job(
        _post_content,
        IntervalTrigger(hours=int(hours)),
        id=jid, args=[channel_id], replace_existing=True)


def deactivate_channel_scheduler(channel_id):
    jid = f"ch_{channel_id}"
    if scheduler.get_job(jid):
        scheduler.remove_job(jid)


def activate_adhkar_scheduler(channel_id, adhkar_type, time_str):
    jid = f"adhk_{adhkar_type}_{channel_id}"
    if scheduler.get_job(jid):
        scheduler.remove_job(jid)
    h, mn = map(int, time_str.split(":"))
    scheduler.add_job(
        _post_adhkar_job,
        CronTrigger(hour=h, minute=mn),
        id=jid, args=[channel_id, adhkar_type], replace_existing=True)


def deactivate_adhkar_scheduler(channel_id, adhkar_type):
    jid = f"adhk_{adhkar_type}_{channel_id}"
    if scheduler.get_job(jid):
        scheduler.remove_job(jid)


def restore_all_schedulers():
    """استعادة جميع المجدولات من قاعدة البيانات بعد إعادة التشغيل"""
    conn = db()
    rows = conn.execute("SELECT * FROM channel_settings").fetchall()
    conn.close()
    for r in rows:
        cid = r[0]
        if r[2]:   activate_channel_scheduler(cid, r[3])
        # أعمدة الأذكار: post_morning=7, morning_time=8, post_evening=9, evening_time=10, post_sleep=11, sleep_time=12
        if r[7]:   activate_adhkar_scheduler(cid, "morning", r[8])
        if r[9]:   activate_adhkar_scheduler(cid, "evening", r[10])
        if r[11]:  activate_adhkar_scheduler(cid, "sleep",   r[12])
    print("✅ تمت استعادة المجدولات")


# ══════════════════════════════════════════════════
#            معالجات الرسائل النصية
# ══════════════════════════════════════════════════

@bot.message_handler(content_types=["text"])
def on_text(msg):
    user = msg.from_user
    register_user(user)
    cid  = msg.chat.id
    uid  = user.id
    text = msg.text.strip()

    # فحص الاشتراك
    if uid != ADMIN_ID and not is_subscribed(uid):
        demand_subscription(cid)
        return

    st = get_state(uid)

    # ── حالات الانتظار ──────────────────────────
    if st["state"] == "wait_channel":
        _handle_add_channel(msg); return
    if st["state"] == "wait_broadcast":
        _handle_broadcast(msg); return
    if st["state"] == "wait_search_surah":
        _handle_search_surah(msg); return
    if st["state"] == "wait_reminder_time":
        _handle_reminder_time(msg); return
    if st["state"] in ("wait_morning_time", "wait_evening_time", "wait_sleep_time"):
        _handle_adhkar_time(msg, st); return

    # ── القائمة الرئيسية ────────────────────────
    if text == "📖 القرآن الكريم":       _show_ayah(cid)
    elif text == "📜 الأحاديث":           _show_hadith(cid)
    elif text == "📿 الأذكار":            _show_adhkar_menu(cid)
    elif text == "⚙️ إعدادات قناتي":     _show_channels(cid, uid)
    elif text == "⭐ المفضلة":            _show_favorites(cid, uid)
    elif text == "🔔 التذكير اليومي":    _show_reminder(cid, uid)
    elif text == "ℹ️ معلومات":           _show_info(cid)
    elif text == "👑 لوحة الإدارة" and uid == ADMIN_ID:
        _show_admin(cid)
    else:
        _send_main_menu(cid, user.first_name)


# ══════════════════════════════════════════════════
#              عروض الشاشات
# ══════════════════════════════════════════════════

def _send_main_menu(cid, name=""):
    kb = kb_main_admin() if cid == ADMIN_ID else kb_main()

    msg = f"""
🌙 *{greet()}* {name} 🤍

━━━━━━━━━━━━━━━━━━
📱 *مرحباً بك في البوت الإسلامي*

هذا البوت صُمم ليكون رفيقك اليومي في:
📖 تلاوة القرآن الكريم
📜 الأحاديث النبوية الصحيحة
📿 الأذكار اليومية
🤲 الأدعية المتنوعة

━━━━━━━━━━━━━━━━━━
📡 *ميزة النشر التلقائي*
يمكنك ربط البوت بقناتك على تيليغرام
ليقوم بـ:
✔ نشر آيات بشكل تلقائي
✔ نشر أحاديث يومية
✔ نشر أذكار (صباح / مساء / نوم)
✔ جدولة النشر حسب رغبتك

━━━━━━━━━━━━━━━━━━
✨ اختر من القائمة بالأسفل للبدء
"""

    bot.send_message(
        cid,
        msg,
        parse_mode="Markdown",
        reply_markup=kb,
    )

def _show_ayah(cid):
    lm = bot.send_message(cid, "⏳ جاري جلب آية كريمة…")
    ayah = get_random_ayah()
    text = fmt_ayah(ayah)
    try: bot.delete_message(cid, lm.message_id)
    except: pass
    bot.send_message(cid, text, parse_mode="Markdown", reply_markup=kb_quran())


def _show_hadith(cid):
    hadith = get_random_hadith()
    bot.send_message(cid, fmt_hadith(hadith), parse_mode="Markdown", reply_markup=kb_hadith())


def _show_adhkar_menu(cid):
    bot.send_message(
        cid, "📿 *قسم الأذكار والأدعية*\n\nاختر نوع الذكر:",
        parse_mode="Markdown", reply_markup=kb_adhkar_menu())


def _show_channels(cid, uid):
    conn = db()
    cnt  = conn.execute(
        "SELECT COUNT(*) FROM channels WHERE user_id=?", (uid,)
    ).fetchone()[0]
    conn.close()
    if cnt == 0:
        msg = ("📡 *قنواتك*\n\nلا توجد قنوات مضافة بعد!\n\n"
               "لإضافة قناة:\n"
               "١. أضف البوت كأدمن في قناتك\n"
               "٢. اضغط ➕ إضافة قناة جديدة\n"
               "٣. أرسل يوزر القناة أو رابطها")
    else:
        msg = f"📡 *قنواتك* ({cnt} قناة)\n\nاختر قناة للإعدادات:"
    bot.send_message(cid, msg, parse_mode="Markdown", reply_markup=kb_channels(uid))


def _show_favorites(cid, uid):
    conn = db()
    cnt  = conn.execute(
        "SELECT COUNT(*) FROM favorites WHERE user_id=?", (uid,)
    ).fetchone()[0]
    conn.close()
    if cnt == 0:
        bot.send_message(cid, "⭐ *المفضلة*\n\nلا يوجد محفوظات بعد!",
                         parse_mode="Markdown", reply_markup=kb_back_main())
        return
    kb, _ = kb_favorites(uid)
    bot.send_message(cid, f"⭐ *المفضلة* ({cnt} عنصر):",
                     parse_mode="Markdown", reply_markup=kb)


def _show_reminder(cid, uid):
    bot.send_message(cid, "🔔 *إعدادات التذكير*\n\nخصّص تذكيرك اليومي:",
                     parse_mode="Markdown", reply_markup=kb_reminder(uid))


def _show_info(cid):
    bot.send_message(cid, (
        "ℹ️ *معلومات البوت الإسلامي*\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📖 *القرآن الكريم* – آيات عشوائية\n"
        "📜 *الأحاديث* – صحيح البخاري\n"
        "📿 *الأذكار* – صباح، مساء، نوم\n"
        "📡 *إدارة القنوات* – نشر تلقائي\n"
        "⭐ *المفضلة* – احفظ ما يعجبك\n"
        "🔔 *تذكير يومي* – آية في وقتك\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🔗 قناتنا: {CHANNEL_USERNAME}\n"
        "💡 لدعم أفضل تواصل مع الأدمن"
    ), parse_mode="Markdown", reply_markup=kb_back_main())


def _show_admin(cid):
    conn = db()
    u  = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    ch = conn.execute("SELECT COUNT(*) FROM channels").fetchone()[0]
    ac = conn.execute(
        "SELECT COUNT(*) FROM channel_settings WHERE is_active=1"
    ).fetchone()[0]
    conn.close()
    bot.send_message(cid, (
        "👑 *لوحة الإدارة*\n\n"
        f"👥 المستخدمون: *{u}*\n"
        f"📡 القنوات الكلية: *{ch}*\n"
        f"✅ القنوات النشطة: *{ac}*\n\n"
        "اختر من الخيارات:"
    ), parse_mode="Markdown", reply_markup=kb_admin())


# ══════════════════════════════════════════════════
#              معالجات الإدخال (States)
# ══════════════════════════════════════════════════

def _handle_add_channel(msg):
    uid = msg.from_user.id
    cid = msg.chat.id
    txt = msg.text.strip()
    clear_state(uid)

    # normalize username
    if txt.startswith("https://t.me/"):
        uname = "@" + txt.replace("https://t.me/", "").rstrip("/")
    elif not txt.startswith("@"):
        uname = "@" + txt
    else:
        uname = txt

    try:
        chat  = bot.get_chat(uname)
        ch_id = str(chat.id)
        title = chat.title or uname

        me = bot.get_me()
        bm = bot.get_chat_member(ch_id, me.id)
        if bm.status not in ("administrator", "creator"):
            bot.send_message(cid,
                "❌ *البوت ليس أدمن في القناة!*\n\n"
                "أضف البوت كمسؤول أولاً ثم حاول مجدداً.",
                parse_mode="Markdown", reply_markup=kb_main())
            return

        conn = db()
        c    = conn.cursor()
        if c.execute(
            "SELECT id FROM channels WHERE channel_id=? AND user_id=?", (ch_id, uid)
        ).fetchone():
            bot.send_message(cid, "⚠️ هذه القناة مضافة مسبقاً!", reply_markup=kb_main())
            conn.close()
            return

        c.execute("""
            INSERT INTO channels (user_id, channel_id, channel_title, channel_username, added_at)
            VALUES (?,?,?,?,?)""", (uid, ch_id, title, uname, _now()))
        c.execute("""
            INSERT OR IGNORE INTO channel_settings (channel_id, user_id) VALUES (?,?)""",
            (ch_id, uid))
        conn.commit()
        conn.close()

        m2 = types.InlineKeyboardMarkup()
        m2.add(types.InlineKeyboardButton(
            "⚙️ إعدادات القناة", callback_data=f"ch_cfg_{ch_id}"))
        m2.add(types.InlineKeyboardButton(
            "🔙 قائمة القنوات", callback_data="show_channels"))
        bot.send_message(cid,
            f"✅ *تمت إضافة القناة بنجاح!*\n\n📡 *{title}*",
            parse_mode="Markdown", reply_markup=m2)

    except Exception as e:
        bot.send_message(cid,
            "❌ *خطأ في إضافة القناة*\n\n"
            "تأكد من:\n"
            "• صحة يوزر/رابط القناة\n"
            "• إضافة البوت كأدمن",
            parse_mode="Markdown", reply_markup=kb_main())


def _handle_broadcast(msg):
    uid = msg.from_user.id
    cid = msg.chat.id
    if uid != ADMIN_ID:
        clear_state(uid)
        return
    text = msg.text
    clear_state(uid)

    conn = db()
    uids = [r[0] for r in conn.execute(
        "SELECT user_id FROM users WHERE is_blocked=0").fetchall()]
    conn.close()

    ok = fail = 0
    for u in uids:
        try:
            bot.send_message(u, text, parse_mode="Markdown")
            ok += 1
        except:
            fail += 1
        time.sleep(0.05)

    bot.send_message(cid,
        f"📢 *اكتملت الرسالة الجماعية*\n\n✅ نجح: {ok}\n❌ فشل: {fail}",
        parse_mode="Markdown", reply_markup=kb_admin())


def _handle_search_surah(msg):
    uid   = msg.from_user.id
    cid   = msg.chat.id
    query = msg.text.strip()
    clear_state(uid)

    try:
        if query.isdigit():
            ayah = get_ayah_by_surah(int(query))
            if ayah:
                bot.send_message(cid, fmt_ayah(ayah),
                                 parse_mode="Markdown", reply_markup=kb_quran())
                return
        else:
            r = requests.get("https://api.alquran.cloud/v1/surah", timeout=10)
            d = r.json()
            if d.get("code") == 200:
                found = [s for s in d["data"]
                         if query in s["name"] or query.lower() in s["englishName"].lower()]
                if found:
                    s = found[0]
                    m2 = types.InlineKeyboardMarkup()
                    m2.add(types.InlineKeyboardButton(
                        f"📖 عرض آية من {s['name']}", callback_data=f"surah_{s['number']}"))
                    m2.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="rnd_ayah"))
                    bot.send_message(cid,
                        f"🔍 *نتيجة البحث*\n\n"
                        f"📖 *{s['name']}* ({s['englishName']})\n"
                        f"عدد الآيات: {s['numberOfAyahs']}",
                        parse_mode="Markdown", reply_markup=m2)
                    return
    except Exception as e:
        print(f"⚠️  بحث السور: {e}")

    bot.send_message(cid, "❌ لم يتم العثور على السورة.", reply_markup=kb_main())


def _handle_reminder_time(msg):
    uid = msg.from_user.id
    cid = msg.chat.id
    txt = msg.text.strip()
    clear_state(uid)
    try:
        h, mn = map(int, txt.split(":"))
        assert 0 <= h <= 23 and 0 <= mn <= 59
        conn = db()
        conn.execute(
            "UPDATE user_settings SET reminder_time=? WHERE user_id=?", (txt, uid))
        conn.commit(); conn.close()
        bot.send_message(cid, f"✅ تم تعيين وقت التذكير: *{txt}*",
                         parse_mode="Markdown", reply_markup=kb_main())
    except:
        bot.send_message(cid, "❌ صيغة خاطئة. استخدم HH:MM مثل 08:30",
                         reply_markup=kb_main())


def _handle_adhkar_time(msg, st):
    uid = msg.from_user.id
    cid = msg.chat.id
    txt = msg.text.strip()
    channel_id = st["data"].get("channel_id")

    atype_map = {
        "wait_morning_time": ("morning", "morning_time"),
        "wait_evening_time": ("evening", "evening_time"),
        "wait_sleep_time":   ("sleep",   "sleep_time"),
    }
    atype, col = atype_map[st["state"]]
    clear_state(uid)

    try:
        h, mn = map(int, txt.split(":"))
        assert 0 <= h <= 23 and 0 <= mn <= 59
        conn = db()
        conn.execute(
            f"UPDATE channel_settings SET {col}=? WHERE channel_id=?", (txt, channel_id))
        conn.commit(); conn.close()
        activate_adhkar_scheduler(channel_id, atype, txt)
        bot.send_message(cid,
            f"✅ وقت *{_CAT_AR[atype]}*: {txt}",
            parse_mode="Markdown", reply_markup=kb_main())
    except:
        bot.send_message(cid, "❌ صيغة خاطئة. استخدم HH:MM مثل 06:00",
                         reply_markup=kb_main())


# ══════════════════════════════════════════════════
#              معالج الـ Callbacks
# ══════════════════════════════════════════════════

@bot.callback_query_handler(func=lambda c: True)
def on_callback(call):
    user = call.from_user
    register_user(user)
    uid  = user.id
    cid  = call.message.chat.id
    mid  = call.message.message_id
    data = call.data

    # فحص الاشتراك
    if data != "check_sub" and uid != ADMIN_ID and not is_subscribed(uid):
        bot.answer_callback_query(call.id, "❌ يجب الاشتراك في القناة أولاً!")
        return

    # anti-spam
    if not throttle(uid) and data not in ("check_sub",):
        bot.answer_callback_query(call.id, "⏳ انتظر لحظة…")
        return

    # ── Subscription ──────────────────────────────
    if data == "check_sub":
        if is_subscribed(uid):
            bot.answer_callback_query(call.id, "✅ تم التحقق! أهلاً بك 🌙")
            try: bot.delete_message(cid, mid)
            except: pass
            kb = kb_main_admin() if uid == ADMIN_ID else kb_main()
            bot.send_message(cid,
                f"🌙 *{greet()}* {user.first_name}!\n\nأهلاً بك في *البوت الإسلامي* 📱\nاختر من القائمة:",
                parse_mode="Markdown", reply_markup=kb)
        else:
            bot.answer_callback_query(call.id, "❌ لم تشترك بعد!", show_alert=True)
        return

    # ── noop ──────────────────────────────────────
    if data == "noop":
        bot.answer_callback_query(call.id); return

    # ── Back to main ──────────────────────────────
    if data == "back_main":
        try: bot.delete_message(cid, mid)
        except: pass
        kb = kb_main_admin() if uid == ADMIN_ID else kb_main()
        bot.send_message(cid,
            f"🌙 *{greet()}* {user.first_name}!\n\nاختر من القائمة:",
            parse_mode="Markdown", reply_markup=kb)
        bot.answer_callback_query(call.id); return

    # ── Quran ─────────────────────────────────────
    if data == "rnd_ayah":
        bot.answer_callback_query(call.id, "⏳ جاري الجلب…")
        ayah = get_random_ayah()
        _edit_or_send(cid, mid, fmt_ayah(ayah), kb_quran()); return

    if data == "save_ayah":
        ayah = get_random_ayah()
        if ayah:
            save_fav(uid, "ayah", ayah["text"])
            bot.answer_callback_query(call.id, "⭐ تم الحفظ في المفضلة!")
        else:
            bot.answer_callback_query(call.id, "❌ فشل الحفظ")
        return

    if data == "search_surah":
        set_state(uid, "wait_search_surah")
        bot.answer_callback_query(call.id)
        bot.send_message(cid,
            "🔍 *البحث عن سورة*\n\nأرسل اسم السورة أو رقمها (١-١١٤):",
            parse_mode="Markdown", reply_markup=types.ForceReply())
        return

    if data.startswith("surah_"):
        num  = int(data.split("_")[1])
        ayah = get_ayah_by_surah(num)
        bot.answer_callback_query(call.id)
        _edit_or_send(cid, mid, fmt_ayah(ayah), kb_quran()); return

    # ── Hadith ────────────────────────────────────
    if data == "rnd_hadith":
        bot.answer_callback_query(call.id, "⏳ جاري الجلب…")
        _edit_or_send(cid, mid, fmt_hadith(get_random_hadith()), kb_hadith()); return

    if data == "save_hadith":
        h = get_random_hadith()
        if h:
            save_fav(uid, "hadith", h.get("hadith") or h.get("text") or "")
            bot.answer_callback_query(call.id, "⭐ تم الحفظ!")
        else:
            bot.answer_callback_query(call.id, "❌ فشل الحفظ")
        return

    # ── Adhkar ────────────────────────────────────
    if data == "adhkar_menu":
        bot.answer_callback_query(call.id)
        _edit_or_send(cid, mid,
            "📿 *قسم الأذكار والأدعية*\n\nاختر نوع الذكر:", kb_adhkar_menu()); return

    if data.startswith("adhkar_"):
        cat = data.replace("adhkar_", "")
        if cat in ("morning", "evening", "sleep", "misc"):
            bot.answer_callback_query(call.id)
            item = get_adhkar(cat)
            _edit_or_send(cid, mid, fmt_adhkar(item, cat), kb_adhkar_item(cat)); return

    if data.startswith("save_adhkar_"):
        cat  = data.replace("save_adhkar_", "")
        item = get_adhkar(cat)
        if item:
            content = item.get("content") or item.get("text") or ""
            save_fav(uid, "adhkar", content)
            bot.answer_callback_query(call.id, "⭐ تم الحفظ!")
        else:
            bot.answer_callback_query(call.id, "❌ فشل الحفظ")
        return

    # ── Channels ──────────────────────────────────
    if data == "show_channels":
        bot.answer_callback_query(call.id)
        conn = db()
        cnt  = conn.execute(
            "SELECT COUNT(*) FROM channels WHERE user_id=?", (uid,)
        ).fetchone()[0]
        conn.close()
        msg = (f"📡 *قنواتك* ({cnt} قناة)\n\nاختر قناة:" if cnt
               else "📡 لا توجد قنوات مضافة بعد!")
        _edit_or_send(cid, mid, msg, kb_channels(uid)); return

    if data == "add_channel":
        set_state(uid, "wait_channel")
        bot.answer_callback_query(call.id)
        bot.send_message(cid,
            "📡 *إضافة قناة جديدة*\n\n"
            "أرسل يوزر القناة أو رابطها:\n"
            "مثال: @mychannel أو https://t.me/mychannel\n\n"
            "⚠️ تأكد من إضافة البوت كأدمن أولاً!",
            parse_mode="Markdown", reply_markup=types.ForceReply())
        return

    if data.startswith("ch_cfg_"):
        ch_id = data.replace("ch_cfg_", "")
        if not owns_channel(uid, ch_id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية!"); return
        bot.answer_callback_query(call.id)
        kb = kb_ch_settings(ch_id)
        if kb:
            _edit_or_send(cid, mid, ch_settings_msg(ch_id), kb)
        return

    if data.startswith("tg_active_"):
        ch_id = data.replace("tg_active_", "")
        if not owns_channel(uid, ch_id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية!"); return
        new = toggle_col(ch_id, "is_active")
        cs  = _get_cs(ch_id)
        if new:
            activate_channel_scheduler(ch_id, cs[3])
            bot.answer_callback_query(call.id, "▶️ بدأ النشر!")
        else:
            deactivate_channel_scheduler(ch_id)
            bot.answer_callback_query(call.id, "⏸ توقف النشر!")
        _edit_or_send(cid, mid, ch_settings_msg(ch_id), kb_ch_settings(ch_id)); return

    for suffix, col in [("tg_q_", "post_quran"), ("tg_h_", "post_hadith"),
                         ("tg_a_", "post_adhkar"), ("tg_em_", "use_emoji")]:
        if data.startswith(suffix):
            ch_id = data.replace(suffix, "")
            if not owns_channel(uid, ch_id):
                bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية!"); return
            new = toggle_col(ch_id, col)
            bot.answer_callback_query(call.id, "✅ تم" if new else "❌ تم الإيقاف")
            _edit_or_send(cid, mid, ch_settings_msg(ch_id), kb_ch_settings(ch_id)); return

    for suffix, atype in [("tg_m_", "morning"), ("tg_e_", "evening"), ("tg_s_", "sleep")]:
        if data.startswith(suffix):
            ch_id = data.replace(suffix, "")
            if not owns_channel(uid, ch_id):
                bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية!"); return
            col_map = {"morning": "post_morning", "evening": "post_evening", "sleep": "post_sleep"}
            time_col_map = {"morning": 8, "evening": 10, "sleep": 12}
            new = toggle_col(ch_id, col_map[atype])
            cs  = _get_cs(ch_id)
            if new:
                activate_adhkar_scheduler(ch_id, atype, cs[time_col_map[atype]])
                bot.answer_callback_query(call.id, f"✅ تم تفعيل {_CAT_AR[atype]}")
                set_state(uid, f"wait_{atype}_time", {"channel_id": ch_id})
                bot.send_message(cid,
                    f"⏰ أرسل وقت *{_CAT_AR[atype]}* بصيغة HH:MM\nمثال: 06:00",
                    parse_mode="Markdown", reply_markup=types.ForceReply())
            else:
                deactivate_adhkar_scheduler(ch_id, atype)
                bot.answer_callback_query(call.id, f"❌ تم إيقاف {_CAT_AR[atype]}")
            _edit_or_send(cid, mid, ch_settings_msg(ch_id), kb_ch_settings(ch_id)); return

    if data.startswith("set_interval_"):
        ch_id = data.replace("set_interval_", "")
        bot.answer_callback_query(call.id)
        _edit_or_send(cid, mid,
            "⏱ *اختر الفاصل الزمني للنشر:*", kb_interval(ch_id)); return

    if data.startswith("int_"):
        parts  = data.split("_")
        hours  = int(parts[1])
        ch_id  = "_".join(parts[2:])
        if not owns_channel(uid, ch_id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية!"); return
        conn = db()
        conn.execute(
            "UPDATE channel_settings SET interval_hours=? WHERE channel_id=?", (hours, ch_id))
        conn.commit(); conn.close()
        cs = _get_cs(ch_id)
        if cs and cs[2]:
            activate_channel_scheduler(ch_id, hours)
        bot.answer_callback_query(call.id, f"✅ الفاصل: كل {hours} ساعة")
        _edit_or_send(cid, mid, ch_settings_msg(ch_id), kb_ch_settings(ch_id)); return

    if data.startswith("del_ch_"):
        ch_id = data.replace("del_ch_", "")
        if not owns_channel(uid, ch_id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية!"); return
        m2 = types.InlineKeyboardMarkup()
        m2.row(
            types.InlineKeyboardButton("✅ نعم، احذف", callback_data=f"confirm_del_{ch_id}"),
            types.InlineKeyboardButton("❌ إلغاء",     callback_data=f"ch_cfg_{ch_id}"),
        )
        bot.answer_callback_query(call.id)
        _edit_or_send(cid, mid,
            "⚠️ *هل أنت متأكد من حذف هذه القناة؟*\n\nلن يمكن التراجع!", m2); return

    if data.startswith("confirm_del_"):
        ch_id = data.replace("confirm_del_", "")
        if not owns_channel(uid, ch_id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية!"); return
        for at in ("morning", "evening", "sleep"):
            deactivate_adhkar_scheduler(ch_id, at)
        deactivate_channel_scheduler(ch_id)
        conn = db()
        conn.execute("DELETE FROM channel_settings WHERE channel_id=?", (ch_id,))
        conn.execute("DELETE FROM channels WHERE channel_id=? AND user_id=?", (ch_id, uid))
        conn.commit(); conn.close()
        bot.answer_callback_query(call.id, "✅ تم الحذف")
        conn2 = db()
        cnt   = conn2.execute(
            "SELECT COUNT(*) FROM channels WHERE user_id=?", (uid,)
        ).fetchone()[0]
        conn2.close()
        msg = (f"📡 *قنواتك* ({cnt} قناة)\n\nاختر قناة:" if cnt
               else "📡 لا توجد قنوات مضافة بعد!")
        _edit_or_send(cid, mid, msg, kb_channels(uid)); return

    # ── Favorites ─────────────────────────────────
    if data == "clear_favs":
        conn = db()
        conn.execute("DELETE FROM favorites WHERE user_id=?", (uid,))
        conn.commit(); conn.close()
        bot.answer_callback_query(call.id, "✅ تم مسح المفضلة")
        _edit_or_send(cid, mid, "⭐ *المفضلة*\n\nتم مسح المفضلة.", kb_back_main()); return

    if data.startswith("fav_n_") or data.startswith("fav_p_"):
        offset = int(data.split("_")[-1])
        kb, total = kb_favorites(uid, offset)
        bot.answer_callback_query(call.id)
        try: bot.edit_message_reply_markup(cid, mid, reply_markup=kb)
        except: pass
        return

    if data.startswith("vfav_"):
        fid  = int(data.replace("vfav_", ""))
        conn = db()
        row  = conn.execute(
            "SELECT content_type, content FROM favorites WHERE id=?", (fid,)
        ).fetchone()
        conn.close()
        if row:
            m2 = types.InlineKeyboardMarkup()
            m2.add(types.InlineKeyboardButton("🗑 حذف",       callback_data=f"dfav_{fid}"))
            m2.add(types.InlineKeyboardButton("🔙 المفضلة",   callback_data="show_favs"))
            bot.answer_callback_query(call.id)
            bot.send_message(cid, row[1], parse_mode="Markdown", reply_markup=m2)
        return

    if data.startswith("dfav_"):
        fid  = int(data.replace("dfav_", ""))
        conn = db()
        conn.execute("DELETE FROM favorites WHERE id=? AND user_id=?", (fid, uid))
        conn.commit(); conn.close()
        bot.answer_callback_query(call.id, "✅ تم الحذف")
        try: bot.delete_message(cid, mid)
        except: pass
        return

    if data == "show_favs":
        bot.answer_callback_query(call.id)
        _show_favorites(cid, uid); return

    # ── Reminder & Night Mode ─────────────────────
    if data == "tg_reminder":
        conn = db()
        cur  = conn.execute(
            "SELECT daily_reminder FROM user_settings WHERE user_id=?", (uid,)
        ).fetchone()
        new  = 0 if (cur and cur[0]) else 1
        conn.execute(
            "UPDATE user_settings SET daily_reminder=? WHERE user_id=?", (new, uid))
        conn.commit(); conn.close()
        bot.answer_callback_query(call.id, "✅ تم التفعيل" if new else "❌ تم الإيقاف")
        try: bot.edit_message_reply_markup(cid, mid, reply_markup=kb_reminder(uid))
        except: pass
        return

    if data == "set_reminder_time":
        set_state(uid, "wait_reminder_time")
        bot.answer_callback_query(call.id)
        bot.send_message(cid,
            "⏰ أرسل وقت التذكير بصيغة HH:MM\nمثال: 08:30",
            reply_markup=types.ForceReply())
        return

    if data == "tg_nightmode":
        conn = db()
        cur  = conn.execute(
            "SELECT night_mode FROM user_settings WHERE user_id=?", (uid,)
        ).fetchone()
        new  = 0 if (cur and cur[0]) else 1
        conn.execute("UPDATE user_settings SET night_mode=? WHERE user_id=?", (new, uid))
        conn.commit(); conn.close()
        bot.answer_callback_query(call.id, "✅ الوضع الليلي" if new else "☀️ الوضع العادي")
        try: bot.edit_message_reply_markup(cid, mid, reply_markup=kb_reminder(uid))
        except: pass
        return

    # ── Admin ─────────────────────────────────────
    if uid != ADMIN_ID:
        bot.answer_callback_query(call.id); return

    if data == "adm_users":
        conn  = db()
        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        new_t = conn.execute(
            "SELECT COUNT(*) FROM users WHERE joined_at LIKE ?", (today + "%",)
        ).fetchone()[0]
        conn.close()
        bot.answer_callback_query(call.id)
        _edit_or_send(cid, mid,
            f"👥 *إحصائيات المستخدمين*\n\n📊 الإجمالي: *{total}*\n🆕 اليوم: *{new_t}*",
            kb_admin()); return

    if data == "adm_channels":
        conn  = db()
        total = conn.execute("SELECT COUNT(*) FROM channels").fetchone()[0]
        actv  = conn.execute(
            "SELECT COUNT(*) FROM channel_settings WHERE is_active=1"
        ).fetchone()[0]
        top   = conn.execute("""
            SELECT u.first_name, COUNT(ch.id)
            FROM users u JOIN channels ch ON u.user_id=ch.user_id
            GROUP BY u.user_id ORDER BY 2 DESC LIMIT 5""").fetchall()
        conn.close()
        msg = (f"📡 *إحصائيات القنوات*\n\n"
               f"📊 الكلية: *{total}* | ✅ النشطة: *{actv}*\n\n*أكثر المستخدمين قنوات:*\n")
        for name, cnt in top:
            msg += f"• {name}: {cnt} قناة\n"
        bot.answer_callback_query(call.id)
        _edit_or_send(cid, mid, msg, kb_admin()); return

    if data == "adm_broadcast":
        set_state(uid, "wait_broadcast")
        bot.answer_callback_query(call.id)
        bot.send_message(cid,
            "📢 أرسل الرسالة الجماعية (تدعم Markdown):",
            reply_markup=types.ForceReply())
        return

    if data == "adm_top":
        conn = db()
        top  = conn.execute("""
            SELECT first_name, last_active FROM users
            ORDER BY last_active DESC LIMIT 10""").fetchall()
        conn.close()
        msg = "🏆 *أنشط المستخدمين*\n\n"
        for i, (name, la) in enumerate(top, 1):
            msg += f"{i}. {name} — {la}\n"
        bot.answer_callback_query(call.id)
        _edit_or_send(cid, mid, msg, kb_admin()); return

    bot.answer_callback_query(call.id)


# ══════════════════════════════════════════════════
#              دوال المساعدة للرسائل
# ══════════════════════════════════════════════════

def _edit_or_send(cid, mid, text, markup):
    try:
        bot.edit_message_text(text, cid, mid,
                              parse_mode="Markdown", reply_markup=markup)
    except Exception:
        bot.send_message(cid, text, parse_mode="Markdown", reply_markup=markup)


# ══════════════════════════════════════════════════
#               نقطة الإطلاق
# ══════════════════════════════════════════════════

def main():
    print("╔═══════════════════════════════╗")
    print("║  🌙 البوت الإسلامي — يبدأ   ║")
    print("╚═══════════════════════════════╝")

    print(f"📁 مسار قاعدة البيانات: {DB_PATH}")
    init_db()
    print("✅ قاعدة البيانات جاهزة")

    print("📥 تحميل الأحاديث…")
    load_hadiths()

    print("📥 تحميل الأذكار…")
    load_adhkar()

    scheduler.start()
    print("✅ المجدوِل يعمل")

    restore_all_schedulers()

    # تذكير يومي: يفحص كل دقيقة
    scheduler.add_job(
        _daily_reminders, "interval", minutes=1, id="daily_reminders")

    print("🤖 البوت يعمل الآن… اضغط Ctrl+C للإيقاف")
    print("=" * 45)

    bot.infinity_polling(timeout=60, long_polling_timeout=60)


if __name__ == "__main__":
    main()