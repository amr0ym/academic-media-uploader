# ==============================================================================
# أداة رفع الفيديوهات المباشرة من SharePoint / OneDrive إلى YouTube
# ==============================================================================

import os
import subprocess
import requests
import argparse

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
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from auth_utils import (
    get_state_dir,
    get_youtube_credentials,
    get_onedrive_access_token,
    refresh_onedrive_access_token_after_401,
)

# ==============================================================================
# إعدادات الفيديو والروابط
# ==============================================================================

# ضع رابط المشاركة أو المشاهدة من SharePoint / OneDrive
VIDEO_URL = "https://onedrive.live.com/"

VIDEO_TITLE = "تجربة رفع فيديو من OneDrive"
VIDEO_DESCRIPTION = "تم الرفع تلقائياً عبر Google Colab"
PRIVACY_STATUS = "unlisted"   # Options: "public" | "unlisted" | "private"

TEMP_DIR = "/content/temp_single_video"
os.makedirs(TEMP_DIR, exist_ok=True)
OUTPUT_PATH = os.path.join(TEMP_DIR, "test_video.mp4")

# ==============================================================================
# دعم تمرير المدخلات عبر args/env مع الحفاظ على الإعدادات الحالية
# ==============================================================================
parser = argparse.ArgumentParser(description="رفع فيديو من OneDrive/SharePoint إلى YouTube")
parser.add_argument("--video-url", default=os.getenv("ONEDRIVE_VIDEO_URL", VIDEO_URL))
parser.add_argument("--video-title", default=os.getenv("ONEDRIVE_VIDEO_TITLE", VIDEO_TITLE))
parser.add_argument("--video-description", default=os.getenv("ONEDRIVE_VIDEO_DESCRIPTION", VIDEO_DESCRIPTION))
parser.add_argument(
    "--privacy-status",
    default=os.getenv("ONEDRIVE_PRIVACY_STATUS", PRIVACY_STATUS),
    choices=["public", "unlisted", "private"]
)
args = parser.parse_args()

VIDEO_URL = args.video_url
VIDEO_TITLE = args.video_title
VIDEO_DESCRIPTION = args.video_description
PRIVACY_STATUS = args.privacy_status

# ==============================================================================
# 2. المصادقة وتوثيق الاتصال بـ YouTube API
# ==============================================================================

drive.mount('/content/mydrive', force_remount=False)

STATE_DIR = get_state_dir()

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube"
]

credentials = get_youtube_credentials(SCOPES, provider_label="OneDrive/YouTube")

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

onedrive_access_token, onedrive_oauth_mode = get_onedrive_access_token()
if onedrive_access_token:
    headers["Authorization"] = "Bearer " + onedrive_access_token
    print("تم تفعيل OneDrive OAuth token المخزن تلقائياً.")
elif onedrive_oauth_mode:
    print(
        "تنبيه: إعدادات OAuth لـ OneDrive موجودة لكن لم يتم استخراج access token صالح. "
        "سيتم المحاولة بالرابط المباشر فقط."
    )
    print(
        "للمرة الأولى عند استخدام OAuth مع OneDrive يلزم إجراء يدوي خارجي للحصول على refresh token "
        "ووضعه في Colab Secrets (ONEDRIVE_CLIENT_ID / ONEDRIVE_REFRESH_TOKEN)."
    )

response = requests.get(download_url, stream=True, allow_redirects=True, headers=headers, timeout=60)
if response.status_code == 401 and onedrive_oauth_mode:
    print("تم رفض access token الحالي (401). جاري محاولة تحديث التوكن وإعادة المحاولة...")
    try:
        refreshed_access_token = refresh_onedrive_access_token_after_401()
    except Exception as exc:
        raise RuntimeError(
            "فشل تحديث OneDrive OAuth token بعد انتهاء/إلغاء الصلاحية. "
            "تحقق من ONEDRIVE_REFRESH_TOKEN و ONEDRIVE_CLIENT_ID."
        ) from exc
    headers["Authorization"] = "Bearer " + refreshed_access_token
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
