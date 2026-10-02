import json
from copy import deepcopy
from io import BytesIO

import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

NAMESPACE = "daily_huddle"


def _service():
    info = dict(st.secrets["google_service_account"])

    creds = service_account.Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/drive"]
    )

    return build(
        "drive",
        "v3",
        credentials=creds,
        cache_discovery=False
    )


def _find_file():
    service = _service()

    folder_id = st.secrets["google_drive"]["folder_id"]
    file_name = st.secrets["google_drive"]["file_name"]

    query = (
        f"name='{file_name}' and "
        f"'{folder_id}' in parents and "
        f"trashed=false"
    )

    result = service.files().list(
        q=query,
        fields="files(id,name)"
    ).execute()

    files = result.get("files", [])

    if not files:
        raise FileNotFoundError(
            f"{file_name} not found"
        )

    return files[0]["id"]


def load_root():
    try:
        file_id = _find_file()

        raw = (
            _service()
            .files()
            .get_media(fileId=file_id)
            .execute()
        )

        return json.loads(raw.decode("utf-8"))

    except Exception as exc:
        st.error(f"Google Drive load failed: {exc}")
        return {}


def save_root(root):
    file_id = _find_file()

    payload = json.dumps(
        root,
        indent=2,
        ensure_ascii=False
    ).encode("utf-8")

    media = MediaIoBaseUpload(
        BytesIO(payload),
        mimetype="application/json",
        resumable=False,
    )

    (
        _service()
        .files()
        .update(
            fileId=file_id,
            media_body=media
        )
        .execute()
    )


def load_huddle(date_key, session="BOTH"):
    root = load_root()

    return deepcopy(
        root.get(NAMESPACE, {})
        .get("records", {})
        .get(f"{date_key}|{session}", {})
    )


def save_huddle(date_key, session, record):
    root = load_root()

    root.setdefault(
        NAMESPACE,
        {}
    ).setdefault(
        "records",
        {}
    )[f"{date_key}|{session}"] = record

    save_root(root)


def load_exceptions():
    root = load_root()

    return deepcopy(
        root.get(NAMESPACE, {})
        .get("exceptions", [])
    )


def save_exceptions(items):
    root = load_root()

    root.setdefault(
        NAMESPACE,
        {}
    )["exceptions"] = items

    save_root(root)
