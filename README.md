# StaffHuddle

Standalone Streamlit Daily Huddle app.

## Deploy
1. Upload these files to `jhsacks/StaffHuddle`.
2. In Streamlit Community Cloud, create an app using `app.py`.
3. Copy your **existing** Google Drive service-account credentials and existing JSON file ID into Streamlit app Secrets using `secrets.example.toml` as the template.
4. Share the existing Google Drive JSON file with the service account email as Editor.

The app preserves all existing root JSON keys and writes only under `daily_huddle`.

## Data safety
Do not commit `.streamlit/secrets.toml` or service-account JSON credentials.
