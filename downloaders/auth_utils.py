import glob
import json
import os
import pickle
import sys
import time
from typing import Optional, Tuple

import requests
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow


DEFAULT_STATE_DIR = "/content/mydrive/MyDrive/YT_Uploader"


def get_state_dir() -> str:
    state_dir = os.getenv("AUTH_STATE_DIR", DEFAULT_STATE_DIR)
    os.makedirs(state_dir, exist_ok=True)
    return state_dir


def find_client_secret_file(state_dir: str) -> str:
    explicit = os.getenv("YOUTUBE_CLIENT_SECRET_FILE")
    if explicit:
        if os.path.exists(explicit):
            return explicit
        raise FileNotFoundError(f"YOUTUBE_CLIENT_SECRET_FILE غير موجود: {explicit}")

    possible_paths = [
        "/content/client_secret.json",
        os.path.join(state_dir, "client_secret.json"),
    ]
    for p in possible_paths:
        if os.path.exists(p):
            return p

    matched = glob.glob("/content/client_secret*.json") + glob.glob(os.path.join(state_dir, "client_secret*.json"))
    if matched:
        return matched[0]

    raise FileNotFoundError(
        "لم يتم العثور على client_secret.json. أضف الملف إلى /content/ أو داخل AUTH_STATE_DIR."
    )


def get_youtube_credentials(scopes, provider_label: str = "YouTube"):
    state_dir = get_state_dir()
    token_file = os.getenv("YOUTUBE_TOKEN_FILE", os.path.join(state_dir, "youtube_token.pickle"))
    client_secret_file = find_client_secret_file(state_dir)

    credentials = None
    if os.path.exists(token_file):
        try:
            with open(token_file, "rb") as f:
                credentials = pickle.load(f)
        except Exception as exc:
            print(f"تحذير: فشل قراءة ملف التوكن المحفوظ ({token_file}): {exc}")
            credentials = None

    if credentials and credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
            with open(token_file, "wb") as f:
                pickle.dump(credentials, f)
            print("تم تحديث توكن YouTube تلقائياً باستخدام refresh token.")
        except Exception as exc:
            print(f"تحذير: فشل تحديث توكن YouTube المحفوظ: {exc}")
            credentials = None

    if credentials and credentials.valid:
        return credentials

    if not sys.stdin.isatty():
        raise RuntimeError(
            f"لا يوجد توكن صالح لـ {provider_label} في الوضع غير التفاعلي. "
            "نفّذ أول مصادقة مرة واحدة بشكل تفاعلي لإنشاء youtube_token.pickle داخل AUTH_STATE_DIR."
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        client_secret_file, scopes, redirect_uri="urn:ietf:wg:oauth:2.0:oob"
    )
    auth_url, _ = flow.authorization_url(prompt="consent")
    print(
        "\nمطلوب إجراء يدوي لأول مرة فقط: افتح رابط المصادقة التالي، وافق على الصلاحيات، "
        "ثم الصق كود التوثيق هنا.\n"
    )
    print(auth_url)
    code = input("أدخل كود التوثيق: ").strip()
    if not code:
        raise RuntimeError("لم يتم إدخال كود التوثيق.")

    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        raise RuntimeError(f"فشل الحصول على توكن OAuth. قد يكون الكود منتهي/غير صحيح: {exc}") from exc

    credentials = flow.credentials
    os.makedirs(os.path.dirname(token_file), exist_ok=True)
    with open(token_file, "wb") as f:
        pickle.dump(credentials, f)
    print(f"تم حفظ توكن YouTube في: {token_file}")
    return credentials


def _load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_json(path: str, data: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def get_onedrive_token_file() -> str:
    state_dir = get_state_dir()
    return os.getenv("ONEDRIVE_TOKEN_FILE", os.path.join(state_dir, "onedrive_token.json"))


def _refresh_onedrive_access_token(token_payload: dict) -> dict:
    tenant = os.getenv("ONEDRIVE_TENANT_ID", "common")
    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    response = requests.post(token_url, data=token_payload, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"فشل تحديث توكن OneDrive. HTTP {response.status_code}: {response.text[:300]}")
    return response.json()


def get_onedrive_access_token() -> Tuple[Optional[str], bool]:
    """
    returns: (access_token, oauth_mode_enabled)
    """
    explicit_access_token = os.getenv("ONEDRIVE_ACCESS_TOKEN", "").strip()
    if explicit_access_token:
        return explicit_access_token, True

    token_file = get_onedrive_token_file()
    token_data = _load_json(token_file)
    now = int(time.time())

    cached_access = str(token_data.get("access_token", "")).strip()
    expires_at = int(token_data.get("expires_at", 0) or 0)
    if cached_access and expires_at > (now + 60):
        return cached_access, True

    refresh_token = str(os.getenv("ONEDRIVE_REFRESH_TOKEN", token_data.get("refresh_token", ""))).strip()
    client_id = str(os.getenv("ONEDRIVE_CLIENT_ID", token_data.get("client_id", ""))).strip()
    client_secret = str(os.getenv("ONEDRIVE_CLIENT_SECRET", token_data.get("client_secret", ""))).strip()

    oauth_mode = bool(client_id or refresh_token or token_data)
    if not oauth_mode:
        return None, False

    if not refresh_token or not client_id:
        raise RuntimeError(
            "وضع OneDrive OAuth مفعل لكن بيانات التحديث ناقصة. "
            "حدد ONEDRIVE_CLIENT_ID و ONEDRIVE_REFRESH_TOKEN (واختيارياً ONEDRIVE_CLIENT_SECRET)."
        )

    payload = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": "offline_access Files.Read",
    }
    if client_secret:
        payload["client_secret"] = client_secret

    token_response = _refresh_onedrive_access_token(payload)
    new_access = str(token_response.get("access_token", "")).strip()
    new_refresh = str(token_response.get("refresh_token", refresh_token)).strip()
    expires_in = int(token_response.get("expires_in", 3600) or 3600)

    if not new_access:
        raise RuntimeError("فشل تحديث توكن OneDrive: لم يتم إرجاع access_token.")

    save_data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": new_refresh,
        "access_token": new_access,
        "expires_at": now + max(expires_in - 30, 60),
    }
    _save_json(token_file, save_data)
    return new_access, True


def refresh_onedrive_access_token_after_401() -> str:
    token_file = get_onedrive_token_file()
    token_data = _load_json(token_file)

    refresh_token = str(os.getenv("ONEDRIVE_REFRESH_TOKEN", token_data.get("refresh_token", ""))).strip()
    client_id = str(os.getenv("ONEDRIVE_CLIENT_ID", token_data.get("client_id", ""))).strip()
    client_secret = str(os.getenv("ONEDRIVE_CLIENT_SECRET", token_data.get("client_secret", ""))).strip()

    if not refresh_token or not client_id:
        raise RuntimeError("تعذر تحديث OneDrive token بعد 401: missing ONEDRIVE_CLIENT_ID/ONEDRIVE_REFRESH_TOKEN.")

    payload = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": "offline_access Files.Read",
    }
    if client_secret:
        payload["client_secret"] = client_secret

    token_response = _refresh_onedrive_access_token(payload)
    new_access = str(token_response.get("access_token", "")).strip()
    new_refresh = str(token_response.get("refresh_token", refresh_token)).strip()
    expires_in = int(token_response.get("expires_in", 3600) or 3600)
    if not new_access:
        raise RuntimeError("تعذر تحديث OneDrive token بعد 401: الاستجابة لا تحتوي access_token.")

    now = int(time.time())
    _save_json(
        token_file,
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": new_refresh,
            "access_token": new_access,
            "expires_at": now + max(expires_in - 30, 60),
        },
    )
    return new_access
