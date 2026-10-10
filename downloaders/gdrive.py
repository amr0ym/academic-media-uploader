# ==============================================================================
# تجربة رفع فيديو واحد مباشر من Google Drive إلى YouTube (معدّل)
# ==============================================================================
import os
import re
import json
import time
import pickle
import glob
import subprocess
import argparse

# 1. تثبيت وتحديث المكتبات المطلوبة
subprocess.run(["pip", "-q", "install", "-U", "gdown", "google-api-python-client", "google-auth-oauthlib", "google-auth-httplib2"])

import gdown
from google.colab import drive
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ------------------------------------------------------------------------------
# إعدادات الفيديو المنفرد
# ------------------------------------------------------------------------------
# ضع رابط الفيديو المنفرد من Google Drive هنا
VIDEO_URL = "https://drive.google.com/file/"

# بيانات الفيديو على يوتيوب
VIDEO_TITLE = "تجربة رفع فيديو منفرد"
VIDEO_DESCRIPTION = "تم الرفع تلقائياً عبر Colab"
PRIVACY_STATUS = "unlisted"  # "public" | "unlisted" | "private"

TEMP_DIR = "/content/temp_single_video"
os.makedirs(TEMP_DIR, exist_ok=True)

# ------------------------------------------------------------------------------
# دعم تمرير المدخلات عبر args/env مع الحفاظ على الإعدادات الحالية
# ------------------------------------------------------------------------------
parser = argparse.ArgumentParser(description="رفع فيديو من Google Drive إلى YouTube")
parser.add_argument("--video-url", default=os.getenv("GDRIVE_VIDEO_URL", VIDEO_URL))
parser.add_argument("--video-title", default=os.getenv("GDRIVE_VIDEO_TITLE", VIDEO_TITLE))
parser.add_argument("--video-description", default=os.getenv("GDRIVE_VIDEO_DESCRIPTION", VIDEO_DESCRIPTION))
parser.add_argument(
    "--privacy-status",
    default=os.getenv("GDRIVE_PRIVACY_STATUS", PRIVACY_STATUS),
    choices=["public", "unlisted", "private"]
)
args = parser.parse_args()

VIDEO_URL = args.video_url
VIDEO_TITLE = args.video_title
VIDEO_DESCRIPTION = args.video_description
PRIVACY_STATUS = args.privacy_status

# ------------------------------------------------------------------------------
# 2. المصادقة والاتصال بـ YouTube API
# ------------------------------------------------------------------------------
drive.mount('/content/mydrive', force_remount=False)

STATE_DIR = "/content/mydrive/MyDrive/YT_Uploader"
TOKEN_FILE = os.path.join(STATE_DIR, "youtube_token.pickle")

CLIENT_SECRET_FILE = None
if os.path.exists("/content/client_secret.json"):
    CLIENT_SECRET_FILE = "/content/client_secret.json"
else:
    matched_files = glob.glob("/content/client_secret*.json")
    if matched_files:
        CLIENT_SECRET_FILE = matched_files[0]

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
    print("اضغط على الرابط للمصادقة:\n", auth_url)
    code = input("أدخل كود التوثيق هنا: ").strip()
    flow.fetch_token(code=code)
    credentials = flow.credentials
    with open(TOKEN_FILE, "wb") as f:
        pickle.dump(credentials, f)

youtube = build("youtube", "v3", credentials=credentials)
print("تم الاتصال بـ YouTube بنجاح.")

# ------------------------------------------------------------------------------
# 3. استخراج File ID والتنزيل من Google Drive
# ------------------------------------------------------------------------------
print("\nجاري تنزيل الفيديو إلى كولاب...")
output_path = os.path.join(TEMP_DIR, "test_video.mp4")

# استخراج الـ ID من الرابط
file_id_match = re.search(r'd/([a-zA-Z0-9_-]+)', VIDEO_URL) or re.search(r'id=([a-zA-Z0-9_-]+)', VIDEO_URL)

if file_id_match:
    file_id = file_id_match.group(1)
    downloaded_path = gdown.download(id=file_id, output=output_path, quiet=False)
else:
    downloaded_path = gdown.download(url=VIDEO_URL, output=output_path, quiet=False)

if not downloaded_path or not os.path.exists(downloaded_path):
    raise FileNotFoundError("فشل تنزيل الفيديو. تأكد من أن الرابط يحتوي على صلاحية الوصول (Anyone with link).")

print(f"\nتم تنزيل الفيديو بنجاح (الحجم: {round(os.path.getsize(downloaded_path) / (1024*1024), 2)} MB)")

# ------------------------------------------------------------------------------
# 4. رفع الفيديو إلى YouTube
# ------------------------------------------------------------------------------
print("\nجاري رفع الفيديو إلى قناة يوتيوب...")

body = {
    "snippet": {
        "title": VIDEO_TITLE,
        "description": VIDEO_DESCRIPTION,
        "categoryId": "27"  # Education
    },
    "status": {
        "privacyStatus": PRIVACY_STATUS,
        "selfDeclaredMadeForKids": False
    }
}

media = MediaFileUpload(downloaded_path, chunksize=8 * 1024 * 1024, resumable=True)
request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

response = None
while response is None:
    status, response = request.next_chunk()
    if status:
        print(f"تقدم الرفع: {int(status.progress() * 100)}%")

video_id = response["id"]
print("\n" + "="*60)
print(f"تم الرفع بنجاح!")
print(f"رابط الفيديو: https://www.youtube.com/watch?v={video_id}")
print("="*60)

# تنظيف الملف المؤقت
if os.path.exists(downloaded_path):
    os.remove(downloaded_path)
