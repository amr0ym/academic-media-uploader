
# ==============================================================================
# رفع أي فيديو من تلغرام إلى YouTube عبر Colab السحابي (بدون استهلاك الباقة)
# ==============================================================================
import os
import asyncio
import subprocess
import argparse
import sys

# 1. تثبيت وتحديث المكتبات المطلوبة داخل بيئة Colab
subprocess.run([
    "pip", "-q", "install", "-U",
    "telethon", "google-api-python-client", "google-auth-oauthlib", "google-auth-httplib2", "nest_asyncio"
], check=True)

import nest_asyncio
nest_asyncio.apply()

from telethon import TelegramClient
from google.colab import drive
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from auth_utils import get_state_dir, get_youtube_credentials

# ------------------------------------------------------------------------------
# 1. الإعدادات والبيانات الخاصّة بك
# ------------------------------------------------------------------------------
API_ID = ""      # يمكن وضع API ID هنا أو عبر TELEGRAM_API_ID أو --telegram-api-id
API_HASH = ""    # يمكن وضع API HASH هنا أو عبر TELEGRAM_API_HASH أو --telegram-api-hash

# رابط المنشور المراد رفعه
TELEGRAM_POST_URL = "https://t.me/AouEgyRecords20_21/1551"

# بيانات الفيديو عند الرفع إلى YouTube
VIDEO_TITLE = "تجربة رفع فيديو من تلغرام"
VIDEO_DESCRIPTION = "تم الرفع تلقائياً عبر Colab من Telegram"
PRIVACY_STATUS = "unlisted"  # اختر: "public" (عام) | "unlisted" (غير مدرج) | "private" (خاص)

TEMP_DIR = "/content/temp_telegram_video"
os.makedirs(TEMP_DIR, exist_ok=True)
OUTPUT_PATH = os.path.join(TEMP_DIR, "tg_video.mp4")

# ------------------------------------------------------------------------------
# دعم تمرير المدخلات عبر args/env مع الحفاظ على الإعدادات الحالية
# ------------------------------------------------------------------------------
parser = argparse.ArgumentParser(description="رفع فيديو من Telegram إلى YouTube")
parser.add_argument("--telegram-post-url", default=os.getenv("TELEGRAM_POST_URL", TELEGRAM_POST_URL))
parser.add_argument("--telegram-api-id", default=os.getenv("TELEGRAM_API_ID", str(API_ID).strip()))
parser.add_argument("--telegram-api-hash", default=os.getenv("TELEGRAM_API_HASH", str(API_HASH).strip()))
parser.add_argument("--video-title", default=os.getenv("TELEGRAM_VIDEO_TITLE", VIDEO_TITLE))
parser.add_argument("--video-description", default=os.getenv("TELEGRAM_VIDEO_DESCRIPTION", VIDEO_DESCRIPTION))
parser.add_argument(
    "--privacy-status",
    default=os.getenv("TELEGRAM_PRIVACY_STATUS", PRIVACY_STATUS),
    choices=["public", "unlisted", "private"]
)
args = parser.parse_args()

TELEGRAM_POST_URL = args.telegram_post_url
VIDEO_TITLE = args.video_title
VIDEO_DESCRIPTION = args.video_description
PRIVACY_STATUS = args.privacy_status

if not args.telegram_api_id or not args.telegram_api_hash:
    raise ValueError("يرجى تحديد TELEGRAM_API_ID و TELEGRAM_API_HASH عبر env أو args أو داخل الملف.")

try:
    API_ID = int(args.telegram_api_id)
except ValueError as exc:
    raise ValueError("TELEGRAM_API_ID يجب أن يكون رقمًا صحيحًا.") from exc

API_HASH = args.telegram_api_hash

# ------------------------------------------------------------------------------
# 2. المصادقة والاتصال بـ YouTube API
# ------------------------------------------------------------------------------
drive.mount('/content/mydrive', force_remount=False)

STATE_DIR = get_state_dir()
TG_SESSION_FILE = os.getenv("TELEGRAM_SESSION_FILE", os.path.join(STATE_DIR, "telegram_session"))

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube"
]

credentials = get_youtube_credentials(SCOPES, provider_label="Telegram/YouTube")

youtube = build("youtube", "v3", credentials=credentials)
print("تم الاتصال بـ YouTube بنجاح.")

# ------------------------------------------------------------------------------
# 3. تنزيل الفيديو عبر Telethon سحابياً مباشرة
# ------------------------------------------------------------------------------
async def download_telegram_video():
    print("\nجاري الاتصال بـ Telegram عبر Telethon...")
    client = TelegramClient(TG_SESSION_FILE, API_ID, API_HASH)
    await client.connect()

    is_authorized = await client.is_user_authorized()
    if not is_authorized:
        if not sys.stdin.isatty():
            await client.disconnect()
            raise RuntimeError(
                "جلسة Telegram غير صالحة أو غير موجودة في الوضع غير التفاعلي. "
                "نفّذ مصادقة Telegram مرة واحدة يدويًا لإنشاء TELEGRAM_SESSION_FILE دائم."
            )

        print(
            "مطلوب إجراء يدوي لأول مرة فقط في Telegram: "
            "أدخل رقم الهاتف وكود التحقق (ورمز 2FA إن وجد) لإنشاء جلسة دائمة."
        )
        await client.start()
        if not await client.is_user_authorized():
            await client.disconnect()
            raise RuntimeError("فشل تسجيل دخول Telegram. تأكد من API ID/HASH ورمز التحقق.")
        print(f"تم حفظ جلسة Telegram الدائمة في: {TG_SESSION_FILE}")

    url_parts = TELEGRAM_POST_URL.strip("/").split("/")
    chat_entity = url_parts[-2]
    message_id = int(url_parts[-1])

    if chat_entity.isdigit() or chat_entity.startswith("-100"):
        chat_entity = int(chat_entity)

    print(f"جاري جلب المنشور رقم {message_id}...")
    message = await client.get_messages(chat_entity, ids=message_id)

    if not message or not message.media:
        raise ValueError("لم يتم العثور على وسائط أو فيديو في هذا المنشور.")

    print("جاري تنزيل الفيديو مباشرة داخل سيرفر Colab...")

    def callback(current, total):
        progress = (current / total) * 100
        print(f"\rنسبة التنزيل إلى Colab: {progress:.1f}%", end="")

    await client.download_media(message, file=OUTPUT_PATH, progress_callback=callback)
    print("\nتم تنزيل الفيديو بنجاح إلى سيرفر Colab!")
    await client.disconnect()

# تشغيل التنزيل
asyncio.run(download_telegram_video())

file_size_mb = os.path.getsize(OUTPUT_PATH) / (1024 * 1024)
print(f"حجم الملف المحمّل: {file_size_mb:.2f} MB")

# ------------------------------------------------------------------------------
# 4. الرفع إلى YouTube
# ------------------------------------------------------------------------------
print("\nجاري رفع الفيديو إلى YouTube...")

body = {
    "snippet": {
        "title": VIDEO_TITLE,
        "description": VIDEO_DESCRIPTION,
        "categoryId": "27"
    },
    "status": {
        "privacyStatus": PRIVACY_STATUS,
        "selfDeclaredMadeForKids": False
    }
}

media = MediaFileUpload(OUTPUT_PATH, chunksize=8 * 1024 * 1024, resumable=True)
request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

response = None
while response is None:
    status, response = request.next_chunk()
    if status:
        print(f"تقدم الرفع إلى يوتيوب: {int(status.progress() * 100)}%")

video_id = response["id"]
print("\n" + "="*60)
print(f"تم الرفع بنجاح!")
print(f"رابط الفيديو على يوتيوب: https://www.youtube.com/watch?v={video_id}")
print("="*60)

# تنظيف الملف المؤقت
if os.path.exists(OUTPUT_PATH):
    os.remove(OUTPUT_PATH)
