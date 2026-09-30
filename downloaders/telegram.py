
# ==============================================================================
# رفع أي فيديو من تلغرام إلى YouTube عبر Colab السحابي (بدون استهلاك الباقة)
# ==============================================================================
import os
import glob
import pickle
import asyncio
import subprocess

# 1. تثبيت وتحديث المكتبات المطلوبة داخل بيئة Colab
subprocess.run([
    "pip", "-q", "install", "-U",
    "telethon", "google-api-python-client", "google-auth-oauthlib", "google-auth-httplib2", "nest_asyncio"
], check=True)

import nest_asyncio
nest_asyncio.apply()

from telethon import TelegramClient
from google.colab import drive
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ------------------------------------------------------------------------------
# 1. الإعدادات والبيانات الخاصّة بك
# ------------------------------------------------------------------------------
API_ID = 38860251
API_HASH = "13317f5e670a85c023bee721186de33f"

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
# 2. المصادقة والاتصال بـ YouTube API
# ------------------------------------------------------------------------------
drive.mount('/content/mydrive', force_remount=False)

STATE_DIR = "/content/mydrive/MyDrive/YT_Uploader"
os.makedirs(STATE_DIR, exist_ok=True)
TOKEN_FILE = os.path.join(STATE_DIR, "youtube_token.pickle")
TG_SESSION_FILE = os.path.join(STATE_DIR, "telegram_session")

CLIENT_SECRET_FILE = None
possible_paths = [
    "/content/client_secret.json",
    os.path.join(STATE_DIR, "client_secret.json")
]

for p in possible_paths:
    if os.path.exists(p):
        CLIENT_SECRET_FILE = p
        break

if not CLIENT_SECRET_FILE:
    matched = glob.glob("/content/client_secret*.json") + glob.glob(f"{STATE_DIR}/client_secret*.json")
    if matched:
        CLIENT_SECRET_FILE = matched[0]

if CLIENT_SECRET_FILE is None:
    raise FileNotFoundError("لم يتم العثور على client_secret.json! أضفه إلى Colab أو ضع الملف داخل مجلد YT_Uploader في Drive.")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube"
]

credentials = None
if os.path.exists(TOKEN_FILE):
    with open(TOKEN_FILE, "rb") as f:
        credentials = pickle.load(f)

if credentials and credentials.expired and credentials.refresh_token:
    credentials.refresh(Request())

if not credentials or not credentials.valid:
    flow = InstalledAppFlow.from_client_secrets_file(
        CLIENT_SECRET_FILE, SCOPES, redirect_uri="urn:ietf:wg:oauth:2.0:oob"
    )
    auth_url, _ = flow.authorization_url(prompt='consent')
    print("اضغط على الرابط للمصادقة مع يوتيوب:\n", auth_url)
    code = input("أدخل كود توثيق يوتيوب هنا: ").strip()
    flow.fetch_token(code=code)
    credentials = flow.credentials
    with open(TOKEN_FILE, "wb") as f:
        pickle.dump(credentials, f)

youtube = build("youtube", "v3", credentials=credentials)
print("تم الاتصال بـ YouTube بنجاح.")

# ------------------------------------------------------------------------------
# 3. تنزيل الفيديو عبر Telethon سحابياً مباشرة
# ------------------------------------------------------------------------------
async def download_telegram_video():
    print("\nجاري الاتصال بـ Telegram عبر Telethon...")
    client = TelegramClient(TG_SESSION_FILE, API_ID, API_HASH)
    await client.start()

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
