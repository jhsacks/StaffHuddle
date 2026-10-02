import json
from copy import deepcopy
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from io import BytesIO

NAMESPACE = "daily_huddle"

def _service():
    info = dict(st.secrets["google_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)

def _file_id():
    return st.secrets["storage"]["drive_file_id"]

def load_root():
    try:
        raw = _service().files().get_media(fileId=_file_id()).execute()
        return json.loads(raw.decode("utf-8")) if raw else {}
    except Exception as exc:
        st.error(f"Google Drive load failed: {exc}")
        return {}

def save_root(root):
    payload = json.dumps(root, indent=2, ensure_ascii=False).encode("utf-8")
    media = MediaIoBaseUpload(BytesIO(payload), mimetype="application/json", resumable=False)
    _service().files().update(fileId=_file_id(), media_body=media).execute()

def load_huddle(date_key, session="BOTH"):
    root = load_root()
    return deepcopy(root.get(NAMESPACE, {}).get("records", {}).get(f"{date_key}|{session}", {}))

def save_huddle(date_key, session, record):
    root = load_root()
    root.setdefault(NAMESPACE, {}).setdefault("records", {})[f"{date_key}|{session}"] = record
    save_root(root)

def load_exceptions():
    root = load_root()
    return deepcopy(root.get(NAMESPACE, {}).get("exceptions", []))

def save_exceptions(items):
    root = load_root()
    root.setdefault(NAMESPACE, {})["exceptions"] = items
    save_root(root)
