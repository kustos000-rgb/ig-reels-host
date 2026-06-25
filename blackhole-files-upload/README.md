# Blackhole Files — YouTube Shorts uploader

Uploads space/astronomy Shorts to the **Blackhole Files** YouTube channel and
generates the title, description, and hashtags automatically from **each video's
transcript** (`.srt`), so the SEO is tailored to what the video actually says.

## How it works

For every video in `videos/`, the script finds the matching transcript by base
name (e.g. `my_clip.mp4` → `my_clip.srt`) and produces:

- **Title** — the transcript's opening hook (your clips start with a strong
  question), cleaned and capped at YouTube's 100-char limit.
- **Description** — a short summary built from the transcript + a follow CTA +
  hashtags.
- **Hashtags** — `#Shorts` + space terms detected in the transcript
  (black hole, gravastar, event horizon, …) + a broad astronomy block.
- **API tags** — keyword tags (`snippet.tags`) for extra discoverability.

After a successful upload the video and its sidecar files (`.srt`, `.mp3`) are
moved into `posted/`.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Create an OAuth client (Desktop app) in the
   [Google Cloud Console](https://console.cloud.google.com/) with the
   **YouTube Data API v3** enabled, download it as `client_secrets.json`, and
   place it next to the script.
3. Put your videos and their matching `.srt` files (same base name) in `videos/`.

## Usage

```bash
python upload_blackhole.py            # upload one (next) pending video
python upload_blackhole.py --all      # upload every pending video
python upload_blackhole.py --dry-run  # print generated SEO, upload nothing
```

The first run opens a browser to authorize the channel; the token is cached in
`token.pickle` for subsequent runs.

> Tip: run `--dry-run` first to review the generated titles/descriptions.

## SEO backends

- **Offline (default)** — no API key, parses the transcript and extracts
  keywords. Good quality because your transcripts open with a clear hook.
- **OpenAI (optional, higher quality)** — let an LLM write the SEO from the full
  transcript:
  ```bash
  export USE_OPENAI=1
  export OPENAI_API_KEY=sk-...
  # optional: export OPENAI_MODEL=gpt-4o-mini
  python upload_blackhole.py --dry-run
  ```
  If the OpenAI call fails for any reason, it automatically falls back to the
  offline generator so uploads never break.

## Configuration

Edit the constants at the top of `upload_blackhole.py`:

- `CATEGORY_ID` — defaults to `28` (Science & Technology).
- `PRIVACY_STATUS` — `public`, `unlisted`, or `private`.
- `VIDEO_EXTS` — accepted video extensions.

Channel-specific hashtags, tags, and CTA lines live at the top of `seo.py`.
