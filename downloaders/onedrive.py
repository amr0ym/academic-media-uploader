# ==============================================================================
# أداة رفع الفيديوهات المباشرة من SharePoint / OneDrive إلى YouTube
# ==============================================================================

import os
import glob
import pickle
import subprocess
import requests

# ------------------------------------------------------------------------------
# 1. تثبيت وتحديث المكتبات
# ------------------------------------------------------------------------------
subprocess.run([
    "pip", "-q", "install", "-U",
    "google-api-python-client",
    "google-auth-oauthlib",
    "google-auth-httplib2"
], check=True)

from google.colab import drive
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ==============================================================================
# إعدادات الفيديو والروابط
# ==============================================================================

# ضع رابط المشاركة أو المشاهدة من SharePoint / OneDrive
VIDEO_URL = "https://arabou-my.sharepoint.com/:v:/g/personal/s24510315eg_std_aou_edu_eg/IQB0tyOygIkGSKAYZZenADYkAfLVKVA562C9fGX-OA44-9k?nav=eyJyZWZlcnJhbEluZm8iOnsicmVmZXJyYWxBcHAiOiJPbmVEcml2ZUZvckJ1c2luZXNzIiwicmVmZXJyYWxBcHBQbGF0Zm9ybSI6IldlYiIsInJlZmVycmFsTW9kZSI6InZpZXciLCJyZWZlcnJhbFZpZXciOiJNeUZpbGVzTGlua0NvcHkifX0&e=DRSepJ"

VIDEO_TITLE = "تجربة رفع فيديو من OneDrive"
VIDEO_DESCRIPTION = "تم الرفع تلقائياً عبر Google Colab"
PRIVACY_STATUS = "unlisted"   # Options: "public" | "unlisted" | "private"

TEMP_DIR = "/content/temp_single_video"
os.makedirs(TEMP_DIR, exist_ok=True)
OUTPUT_PATH = os.path.join(TEMP_DIR, "test_video.mp4")

# ==============================================================================
# 2. المصادقة وتوثيق الاتصال بـ YouTube API
# ==============================================================================

drive.mount('/content/mydrive', force_remount=False)

STATE_DIR = "/content/mydrive/MyDrive/YT_Uploader"
os.makedirs(STATE_DIR, exist_ok=True)
TOKEN_FILE = os.path.join(STATE_DIR, "youtube_token.pickle")

CLIENT_SECRET_FILE = None
if os.path.exists("/content/client_secret.json"):
    CLIENT_SECRET_FILE = "/content/client_secret.json"
else:
    matched_files = glob.glob("/content/client_secret*.json")
    if matched_files:
        CLIENT_SECRET_FILE = matched_files[0]

if CLIENT_SECRET_FILE is None:
    raise FileNotFoundError("لم يتم العثور على client_secret.json في /content/")

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
    auth_url, _ = flow.authorization_url(prompt="consent")
    print("اضغط على الرابط للمصادقة:\n", auth_url)
    code = input("\nأدخل كود التوثيق هنا: ").strip()
    flow.fetch_token(code=code)
    credentials = flow.credentials
    with open(TOKEN_FILE, "wb") as f:
        pickle.dump(credentials, f)

youtube = build("youtube", "v3", credentials=credentials)
print("تم الاتصال بـ YouTube بنجاح.")

# ==============================================================================
# 3. تنزيل الفيديو المباشر عبر إضافة معيار التنزيل التلقائي (&download=1)
# ==============================================================================

print("\nجاري بدء عملية التنزيل المباشر من SharePoint إلى Colab...")

download_url = VIDEO_URL
if "download=1" not in download_url:
    if "?" in download_url:
        download_url += "&download=1"
    else:
        download_url += "?download=1"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

response = requests.get(download_url, stream=True, allow_redirects=True, headers=headers, timeout=60)

if response.status_code != 200:
    raise Exception(f"فشل التنزيل. كود الاستجابة HTTP Status: {response.status_code}")

content_type = response.headers.get("Content-Type", "").lower()
if "text/html" in content_type:
    raise Exception("عفواً، أعاد الخادم صفحة تسجيل دخول HTML بدلاً من ملف الفيديو. يرجى التأكد من صلاحيات المشاركة للرابط.")

total_size = 0
with open(OUTPUT_PATH, "wb") as f:
    for chunk in response.iter_content(chunk_size=2 * 1024 * 1024):
        if chunk:
            f.write(chunk)
            total_size += len(chunk)
            size_mb = total_size / (1024 * 1024)
            print(f"\rتم تنزيل: {size_mb:.2f} MB", end="")

print(f"\nتم التنزيل بنجاح! الحجم الكلي: {total_size / (1024 * 1024):.2f} MB")

# ==============================================================================
# 4. رفع الفيديو إلى YouTube
# ==============================================================================

print("\nجاري رفع الفيديو إلى القناة على YouTube...")

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

media = MediaFileUpload(OUTPUT_PATH, chunksize=8 * 1024 * 1024, resumable=True)
request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

response = None
while response is None:
    status, response = request.next_chunk()
    if status:
        print(f"تقدم الرفع: {int(status.progress() * 100)}%")

# ==============================================================================
# 5. عرض النتيجة والتنظيف
# ==============================================================================

video_id = response["id"]
print("\n" + "=" * 60)
print("تم الرفع إلى YouTube بنجاح!")
print(f"Video ID: {video_id}")
print(f"رابط الفيديو: https://www.youtube.com/watch?v={video_id}")
print("=" * 60)

if os.path.exists(OUTPUT_PATH):
    os.remove(OUTPUT_PATH)
    print("\nتم تنظيف وحذف الملف المؤقت من بيئة Colab.")
