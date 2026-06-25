"""
Blackhole Files — YouTube Shorts uploader.

For each video it finds the matching transcript (.srt, same base name) and
generates a catchy, SEO-optimized title, description, and hashtags from the
TRANSCRIPT (not a static text file). Then it uploads via the YouTube Data API
and moves the posted files aside.

Usage:
    python upload_blackhole.py            # upload one (random) pending video
    python upload_blackhole.py --all      # upload every pending video
    python upload_blackhole.py --dry-run  # show generated SEO, upload nothing

SEO backend:
    Offline by default (no API key needed). For higher-quality SEO set:
        USE_OPENAI=1 and OPENAI_API_KEY=...   (pip install openai)
"""

import os
import sys
import argparse
import shutil
import pickle

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from seo import generate_seo

# ================= CONFIG =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEOS_DIR = os.path.join(BASE_DIR, "videos")
POSTED_DIR = os.path.join(BASE_DIR, "posted")

VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm")
CATEGORY_ID = "28"  # Science & Technology
PRIVACY_STATUS = "public"

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
# ==========================================

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

os.makedirs(VIDEOS_DIR, exist_ok=True)
os.makedirs(POSTED_DIR, exist_ok=True)


# ------------------ YouTube API ------------------
def get_youtube():
    creds = None
    token_path = os.path.join(BASE_DIR, "token.pickle")

    if os.path.exists(token_path):
        with open(token_path, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                os.path.join(BASE_DIR, "client_secrets.json"),
                SCOPES,
            )
            creds = flow.run_local_server(port=0)

        with open(token_path, "wb") as token:
            pickle.dump(creds, token)

    return build("youtube", "v3", credentials=creds)


# ------------------ Helpers ------------------
def find_transcript(video_path):
    """Return the .srt path that shares the video's base name, or None."""
    base = os.path.splitext(video_path)[0]
    for ext in (".srt", ".SRT"):
        candidate = base + ext
        if os.path.exists(candidate):
            return candidate
    return None


def list_pending_videos():
    return sorted(
        f for f in os.listdir(VIDEOS_DIR)
        if f.lower().endswith(VIDEO_EXTS)
    )


def move_posted(video_path):
    """Move the video and its sidecar files (.srt/.mp3) into posted/."""
    base = os.path.splitext(os.path.basename(video_path))[0]
    src_dir = os.path.dirname(video_path)
    for fname in os.listdir(src_dir):
        if os.path.splitext(fname)[0] == base:
            shutil.move(os.path.join(src_dir, fname),
                        os.path.join(POSTED_DIR, fname))


# ------------------ Upload ------------------
def upload_video(youtube, video_path, seo):
    body = {
        "snippet": {
            "title": seo["title"],
            "description": seo["description"],
            "tags": seo["tags"],
            "categoryId": CATEGORY_ID,
        },
        "status": {
            "privacyStatus": PRIVACY_STATUS,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(video_path, resumable=True)
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"   ⏳ Uploading... {int(status.progress() * 100)}%")

    print("✅ Uploaded:", os.path.basename(video_path),
          "→ https://youtu.be/" + response["id"])
    return response


def process_video(youtube, video, dry_run=False):
    video_path = os.path.join(VIDEOS_DIR, video)
    srt_path = find_transcript(video_path)

    if srt_path:
        print(f"📝 Transcript: {os.path.basename(srt_path)}")
    else:
        print("⚠️ No matching .srt found — using filename for SEO.")

    seo = generate_seo(srt_path or "", fallback_name=os.path.splitext(video)[0])

    print(f"\n📌 Video : {video}")
    print(f"🏷️  Title : {seo['title']}")
    print(f"📄 Description:\n{seo['description']}\n")
    print(f"🔖 API tags: {', '.join(seo['tags'])}\n")

    if dry_run:
        print("🔎 Dry run — not uploading.\n")
        return

    if youtube is None:
        youtube = get_youtube()
    try:
        upload_video(youtube, video_path, seo)
    except Exception as e:  # noqa: BLE001
        print("❌ Upload failed:", e)
        return False

    move_posted(video_path)
    print("📂 Moved to posted:", video, "\n")
    return True


# ------------------ Main ------------------
def main():
    parser = argparse.ArgumentParser(description="Blackhole Files uploader")
    parser.add_argument("--all", action="store_true",
                        help="upload every pending video, not just one")
    parser.add_argument("--dry-run", action="store_true",
                        help="generate and print SEO without uploading")
    args = parser.parse_args()

    videos = list_pending_videos()
    if not videos:
        print("⚠️ No videos found in:", VIDEOS_DIR)
        return

    targets = videos if args.all else videos[:1]

    youtube = None
    if not args.dry_run:
        youtube = get_youtube()

    for video in targets:
        process_video(youtube, video, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
