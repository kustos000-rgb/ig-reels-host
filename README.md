# ig-reels-host

Host for Instagram Reels / short videos, plus a script to download videos from
hashtags into [`videos/`](./videos).

## Setup

```bash
pip install -r requirements.txt   # requires Python 3.9+ and ffmpeg
```

## Download videos from a hashtag

```bash
# Up to 10 "top" videos from #funny into ./videos
python download_hashtag.py funny --count 10

# Multiple hashtags, "recent" section, logged in
python download_hashtag.py funny memes --section recent --count 20 --login YOUR_IG_USERNAME

# Download and commit each file (matches the "upload <name>.mp4" history)
python download_hashtag.py cats --commit
```

### Options

| Flag | Default | Description |
| --- | --- | --- |
| `hashtags` | – | One or more hashtags (without `#`). |
| `--count` | `10` | Max videos to download **per hashtag**. |
| `--section` | `top` | `top` or `recent` posts. |
| `--output-dir` | `./videos` | Where to save the `.mp4` files. |
| `--login USERNAME` | – | Log in as this Instagram user. |
| `--commit` | off | `git add` + `git commit` each downloaded video. |

## Authentication

Instagram blocks **anonymous** hashtag browsing, so a login is almost always
required. Provide credentials via either:

1. `--login USERNAME` with the password in `$IG_PASSWORD` (or you'll be prompted), or
2. the `IG_USERNAME` / `IG_PASSWORD` environment variables.

The session is cached under `~/.config/instaloader/session-<username>` so later
runs don't re-authenticate. Two-factor auth is supported (you'll be asked for the
code).

> Use an account you don't mind rate-limiting/locking. Scraping too aggressively
> can trigger Instagram challenges — keep `--count` modest.

## How it works

- Filters each hashtag feed down to **video** posts (Reels).
- Names files after the post caption (sanitized), falling back to the post
  shortcode; collisions are de-duplicated automatically.
- Tracks already-downloaded posts in `videos/.downloaded_shortcodes` so re-runs
  skip what you already have.
