#!/usr/bin/env python3
"""Download videos (Reels) from one or more Instagram hashtags.

Examples:
    # Download up to 10 videos from #funny into ./videos
    python download_hashtag.py funny --count 10

    # Download from several hashtags, logged in (recommended)
    python download_hashtag.py funny memes --count 20 --login your_ig_username

    # Pull "recent" instead of "top" posts and commit each file to git
    python download_hashtag.py cats --section recent --commit

Authentication
--------------
Instagram blocks anonymous hashtag browsing, so a login is almost always
required. Provide credentials in one of these ways (checked in order):

    1. --login USERNAME            (password taken from $IG_PASSWORD, or prompted)
    2. $IG_USERNAME / $IG_PASSWORD environment variables

The first successful login is cached as an Instaloader session file under
~/.config/instaloader so subsequent runs reuse it without re-authenticating.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import instaloader
from instaloader import (
    BadResponseException,
    ConnectionException,
    LoginRequiredException,
    Post,
    QueryReturnedBadRequestException,
    TwoFactorAuthRequiredException,
)

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "videos"
SESSION_DIR = Path.home() / ".config" / "instaloader"
MANIFEST_NAME = ".downloaded_shortcodes"


def slugify(text: str, *, max_length: int = 80) -> str:
    """Build a safe, readable filename stem from a post caption."""
    if not text:
        return ""
    # Keep the first line only; captions can be long paragraphs.
    text = text.strip().splitlines()[0]
    # Drop emoji / symbols but keep letters, numbers and basic punctuation.
    normalized = unicodedata.normalize("NFKC", text)
    cleaned = "".join(
        ch if (ch.isalnum() or ch in " _-") else " "
        for ch in normalized
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.replace(" ", "_")
    return cleaned[:max_length].strip("_")


def load_manifest(output_dir: Path) -> set[str]:
    manifest = output_dir / MANIFEST_NAME
    if not manifest.exists():
        return set()
    return {line.strip() for line in manifest.read_text().splitlines() if line.strip()}


def append_manifest(output_dir: Path, shortcode: str) -> None:
    manifest = output_dir / MANIFEST_NAME
    with manifest.open("a", encoding="utf-8") as fh:
        fh.write(shortcode + "\n")


def unique_path(output_dir: Path, stem: str, shortcode: str) -> Path:
    """Return a non-colliding mp4 path inside output_dir."""
    stem = stem or shortcode
    candidate = output_dir / f"{stem}.mp4"
    if not candidate.exists():
        return candidate
    # Disambiguate with the shortcode, then a counter, if needed.
    candidate = output_dir / f"{stem}_{shortcode}.mp4"
    counter = 1
    while candidate.exists():
        candidate = output_dir / f"{stem}_{shortcode}_{counter}.mp4"
        counter += 1
    return candidate


def make_loader() -> instaloader.Instaloader:
    return instaloader.Instaloader(
        quiet=True,
        download_pictures=False,
        download_videos=True,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        max_connection_attempts=3,
    )


def authenticate(loader: instaloader.Instaloader, username: str | None) -> bool:
    """Log in if credentials are available. Returns True if logged in."""
    username = username or os.environ.get("IG_USERNAME")
    if not username:
        return False

    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    session_file = SESSION_DIR / f"session-{username}"

    if session_file.exists():
        try:
            loader.load_session_from_file(username, str(session_file))
            print(f"[auth] Reusing cached session for @{username}")
            return True
        except Exception as exc:  # noqa: BLE001 - fall back to password login
            print(f"[auth] Cached session unusable ({exc}); logging in fresh")

    password = os.environ.get("IG_PASSWORD")
    if not password:
        import getpass

        password = getpass.getpass(f"Instagram password for @{username}: ")

    try:
        loader.login(username, password)
    except TwoFactorAuthRequiredException:
        code = input("Two-factor code: ").strip()
        loader.two_factor_login(code)

    loader.save_session_to_file(str(session_file))
    print(f"[auth] Logged in as @{username} (session cached)")
    return True


def download_hashtag(
    loader: instaloader.Instaloader,
    hashtag: str,
    *,
    count: int,
    section: str,
    output_dir: Path,
    commit: bool,
) -> int:
    hashtag = hashtag.lstrip("#").lower()
    seen = load_manifest(output_dir)
    downloaded = 0

    print(f"[#{hashtag}] fetching {section} posts (target: {count} videos)")
    ht = instaloader.Hashtag.from_name(loader.context, hashtag)
    posts = ht.get_top_posts() if section == "top" else ht.get_posts_resumable()

    for post in posts:
        if downloaded >= count:
            break
        if not post.is_video:
            continue
        if post.shortcode in seen:
            continue

        stem = slugify(post.caption or "")
        target = unique_path(output_dir, stem, post.shortcode)

        if download_post_video(loader, post, target):
            append_manifest(output_dir, post.shortcode)
            seen.add(post.shortcode)
            downloaded += 1
            print(f"  [{downloaded}/{count}] {target.name}")
            if commit:
                git_commit(output_dir, target)

    print(f"[#{hashtag}] done: {downloaded} new video(s)")
    return downloaded


def download_post_video(
    loader: instaloader.Instaloader, post: Post, target: Path
) -> bool:
    url = post.video_url
    if not url:
        return False
    try:
        loader.download_pic(str(target.with_suffix("")), url, post.date_utc)
    except Exception as exc:  # noqa: BLE001 - skip individual failures
        print(f"  ! failed {post.shortcode}: {exc}")
        return False

    # download_pic infers the extension from the URL; normalise to .mp4.
    produced = target.with_suffix("")
    for path in target.parent.glob(produced.name + ".*"):
        if path != target:
            path.rename(target)
        break
    return target.exists()


def git_commit(output_dir: Path, target: Path) -> None:
    repo_root = output_dir.parent
    rel = target.relative_to(repo_root)
    try:
        subprocess.run(["git", "add", str(rel)], cwd=repo_root, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"upload {target.name}"],
            cwd=repo_root,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"  ! git commit failed: {exc}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download videos (Reels) from Instagram hashtags.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("hashtags", nargs="+", help="Hashtag(s) to download, without '#'")
    parser.add_argument(
        "--count", type=int, default=10, help="Max videos per hashtag (default: 10)"
    )
    parser.add_argument(
        "--section",
        choices=["top", "recent"],
        default="top",
        help="Which posts to pull (default: top)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Where to save videos (default: ./videos)",
    )
    parser.add_argument(
        "--login",
        metavar="USERNAME",
        help="Instagram username to log in as (password via $IG_PASSWORD or prompt)",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="git add + commit each downloaded video",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    loader = make_loader()
    logged_in = authenticate(loader, args.login)
    if not logged_in:
        print(
            "[auth] No credentials provided. Instagram almost always blocks "
            "anonymous hashtag access; if downloads fail, re-run with --login "
            "or set $IG_USERNAME/$IG_PASSWORD.",
            file=sys.stderr,
        )

    total = 0
    try:
        for hashtag in args.hashtags:
            total += download_hashtag(
                loader,
                hashtag,
                count=args.count,
                section=args.section,
                output_dir=args.output_dir,
                commit=args.commit,
            )
    except (LoginRequiredException, QueryReturnedBadRequestException) as exc:
        print(
            f"\nERROR: Instagram requires a login for hashtag access ({exc}).\n"
            "Re-run with --login USERNAME (and $IG_PASSWORD set).",
            file=sys.stderr,
        )
        return 2
    except (ConnectionException, BadResponseException) as exc:
        print(f"\nERROR: Instagram request failed: {exc}", file=sys.stderr)
        return 3

    print(f"\nTotal downloaded: {total} video(s) into {args.output_dir}")
    return 0 if total else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
