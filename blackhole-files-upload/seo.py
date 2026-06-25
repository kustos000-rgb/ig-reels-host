"""
SEO generation for Blackhole Files.

Given a video's transcript (.srt), produce a catchy, SEO-friendly:
  - title       (<= 100 chars, YouTube limit)
  - description (summary + CTA + hashtags)
  - hashtags    (space/astronomy block + keywords detected in the transcript)
  - tags        (list for the YouTube API "snippet.tags" field)

Two backends:
  - offline (default): parses the transcript and extracts keywords. No API key.
  - openai (optional): set USE_OPENAI=1 and OPENAI_API_KEY to let an LLM write
    the title/description/hashtags from the full transcript.
"""

import os
import re
import json
from collections import Counter

# YouTube hard limits
MAX_TITLE = 100
MAX_DESCRIPTION = 5000
MAX_TAGS_CHARS = 480  # YouTube allows ~500 chars total across tags

# ----------------------------------------------------------------------------
# Fixed channel signals
# ----------------------------------------------------------------------------
# Always-present hashtags (#Shorts capital S is required for Shorts classifier)
BASE_HASHTAGS = [
    "#Shorts", "#Space", "#Astronomy", "#BlackHole", "#Universe",
    "#Cosmos", "#Physics", "#Science", "#Astrophysics", "#SpaceFacts",
]

# Always-present API tags
BASE_TAGS = [
    "space", "astronomy", "black hole", "universe", "cosmos",
    "astrophysics", "physics", "science", "space facts", "shorts",
    "black hole files",
]

CTA_LINES = [
    "Follow Blackhole Files for your daily dose of space and the cosmos. 🚀",
    "Subscribe for more mind-bending space facts. 🌌",
    "Follow for more journeys to the edge of the universe. 🪐",
    "Like and subscribe if the cosmos blows your mind. ✨",
    "Follow Blackhole Files — the universe is stranger than you think. 🌠",
]

# Known space terms -> hashtag. Detected as whole phrases in the transcript.
KNOWN_TERMS = {
    "black hole": "#BlackHole",
    "event horizon": "#EventHorizon",
    "singularity": "#Singularity",
    "gravastar": "#Gravastar",
    "grava star": "#Gravastar",
    "neutron star": "#NeutronStar",
    "white dwarf": "#WhiteDwarf",
    "supernova": "#Supernova",
    "dark energy": "#DarkEnergy",
    "dark matter": "#DarkMatter",
    "wormhole": "#Wormhole",
    "big bang": "#BigBang",
    "milky way": "#MilkyWay",
    "galaxy": "#Galaxy",
    "galaxies": "#Galaxy",
    "quasar": "#Quasar",
    "pulsar": "#Pulsar",
    "nebula": "#Nebula",
    "exoplanet": "#Exoplanet",
    "spacetime": "#Spacetime",
    "space time": "#Spacetime",
    "gravity": "#Gravity",
    "gravitational": "#Gravity",
    "relativity": "#Relativity",
    "einstein": "#Einstein",
    "cosmic microwave background": "#CMB",
    "multiverse": "#Multiverse",
    "time dilation": "#TimeDilation",
    "light speed": "#SpeedOfLight",
    "speed of light": "#SpeedOfLight",
    "antimatter": "#Antimatter",
    "string theory": "#StringTheory",
    "quantum": "#QuantumPhysics",
    "expansion of the universe": "#ExpandingUniverse",
    "expanding universe": "#ExpandingUniverse",
    "vacuum energy": "#VacuumEnergy",
}

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "than", "that", "this",
    "these", "those", "is", "are", "was", "were", "be", "been", "being", "to",
    "of", "in", "on", "at", "by", "for", "with", "about", "as", "into", "like",
    "through", "after", "over", "between", "out", "against", "during", "without",
    "before", "under", "around", "among", "it", "its", "they", "them", "their",
    "we", "us", "our", "you", "your", "i", "me", "my", "he", "she", "his", "her",
    "would", "could", "should", "can", "may", "might", "will", "shall", "do",
    "does", "did", "have", "has", "had", "not", "no", "yes", "so", "such", "very",
    "just", "now", "what", "when", "where", "which", "who", "why", "how", "all",
    "any", "both", "each", "few", "more", "most", "other", "some", "only", "own",
    "same", "too", "there", "here", "from", "up", "down", "because", "itself",
    "something", "anything", "nothing", "everything", "much", "many", "way",
    "thing", "things", "really", "actually", "certainly", "simply", "okay",
    "let", "lets", "go", "well", "isnt", "wouldnt", "doesnt", "dont", "thats",
    "youd", "youre", "weve", "they're", "theyre",
}


# ----------------------------------------------------------------------------
# SRT parsing
# ----------------------------------------------------------------------------
def parse_srt(srt_path):
    """Return the full transcript text from an .srt file (no indexes/timestamps)."""
    with open(srt_path, "r", encoding="utf-8-sig", errors="replace") as f:
        raw = f.read()

    lines = []
    for block in re.split(r"\n\s*\n", raw.strip()):
        for row in block.splitlines():
            row = row.strip()
            if not row:
                continue
            if row.isdigit():           # subtitle index
                continue
            if "-->" in row:            # timestamp line
                continue
            lines.append(row)

    text = " ".join(lines)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def split_sentences(text):
    """Naive sentence splitter that keeps the terminating punctuation."""
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


# ----------------------------------------------------------------------------
# Offline SEO
# ----------------------------------------------------------------------------
def _normalize(text):
    return re.sub(r"[^a-z0-9\s]", " ", text.lower())


def detect_known_terms(text):
    """Return hashtags for known space terms, ordered by first appearance."""
    low = " " + _normalize(text) + " "
    found = []
    for phrase, tag in KNOWN_TERMS.items():
        if f" {phrase} " in low and tag not in found:
            found.append(tag)
    return found


def top_keywords(text, limit=4):
    """Frequency-based single-word keywords, minus stopwords/known noise.

    Words that are components of a detected multi-word term (e.g. "black" or
    "hole" when "black hole" was already detected) are excluded so we don't
    emit noisy fragment hashtags like #Black or #Hole.
    """
    detected = detect_known_terms(text)
    detected_words = set()
    inv = {tag: phrase for phrase, tag in KNOWN_TERMS.items()}
    for tag in detected:
        detected_words.update(inv.get(tag, "").split())

    words = _normalize(text).split()
    counts = Counter(
        w for w in words
        if len(w) > 4 and w not in STOPWORDS and w not in detected_words
    )
    return [w for w, _ in counts.most_common(limit)]


def _camel_hashtag(phrase):
    return "#" + "".join(w.capitalize() for w in phrase.split())


def build_hashtags(text, max_tags=15):
    """Ordered, de-duplicated hashtags: base block + transcript-derived."""
    tags = []

    def add(t):
        if t and t.lower() not in {x.lower() for x in tags}:
            tags.append(t)

    add("#Shorts")
    # Specific, transcript-derived terms first (curated for quality), then the
    # broad channel block. Noisy single-word fragments are intentionally not
    # promoted to visible hashtags (they still feed the API tags below).
    for t in detect_known_terms(text):
        add(t)
    for t in BASE_HASHTAGS:
        add(t)

    return tags[:max_tags]


def build_api_tags(text):
    """Tags for snippet.tags, capped to YouTube's ~500 char budget."""
    tags = []

    def add(t):
        t = t.strip().lower()
        if t and t not in tags:
            tags.append(t)

    for phrase in KNOWN_TERMS:
        if f" {phrase} " in " " + _normalize(text) + " ":
            add(phrase)
    for kw in top_keywords(text, limit=6):
        add(kw)
    for t in BASE_TAGS:
        add(t)

    out, total = [], 0
    for t in tags:
        total += len(t) + 1
        if total > MAX_TAGS_CHARS:
            break
        out.append(t)
    return out


def clean_title_text(sentence):
    sentence = sentence.strip().strip('"').strip()
    # Drop filler openers
    sentence = re.sub(r"^(so|now|well|okay|but|and)[,\s]+", "", sentence, flags=re.I)
    sentence = sentence[:1].upper() + sentence[1:] if sentence else sentence
    return sentence


def build_title_offline(text, fallback=""):
    sentences = split_sentences(text)
    # Prefer the opening hook, especially if it's a question.
    candidate = ""
    for s in sentences[:2]:
        s = clean_title_text(s)
        if s:
            candidate = s
            if s.endswith("?"):
                break
    if not candidate:
        candidate = clean_title_text(fallback) or "Blackhole Files"

    if len(candidate) > MAX_TITLE:
        cut = candidate[:MAX_TITLE - 1].rsplit(" ", 1)[0]
        candidate = cut + "…"
    return candidate


def build_description_offline(text, hashtags):
    import random
    sentences = split_sentences(text)
    summary = " ".join(sentences[:3]).strip()
    if len(summary) > 600:
        summary = summary[:599].rsplit(" ", 1)[0] + "…"

    cta = random.choice(CTA_LINES)
    hashtag_line = " ".join(hashtags)

    parts = [p for p in [summary, cta, hashtag_line] if p]
    desc = "\n\n".join(parts)
    return desc[:MAX_DESCRIPTION]


def generate_offline(text, fallback_name=""):
    hashtags = build_hashtags(text)
    return {
        "title": build_title_offline(text, fallback_name),
        "description": build_description_offline(text, hashtags),
        "hashtags": hashtags,
        "tags": build_api_tags(text),
    }


# ----------------------------------------------------------------------------
# OpenAI SEO (optional)
# ----------------------------------------------------------------------------
def generate_openai(text, fallback_name=""):
    """Use an LLM to write SEO from the transcript. Requires OPENAI_API_KEY."""
    from openai import OpenAI  # imported lazily so offline mode needs no install

    client = OpenAI()
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    prompt = (
        "You are an expert YouTube Shorts SEO strategist for a space/astronomy "
        "channel called 'Blackhole Files'. Given the transcript of a short video, "
        "produce JSON with these keys:\n"
        '  "title": a catchy, curiosity-driven, SEO-optimized title <= 100 chars '
        "(prefer a strong hook or question; no clickbait lies).\n"
        '  "description": 2-4 sentence summary of the video in an engaging tone, '
        "followed by a short call-to-action to follow Blackhole Files.\n"
        '  "hashtags": an array of 8-15 relevant hashtags (each starting with #), '
        'always including "#Shorts", mixing broad space tags with specific terms '
        "from the transcript.\n"
        '  "tags": an array of 10-15 lowercase keyword tags for the YouTube API '
        "(no # symbol).\n"
        "Return ONLY valid JSON, no markdown.\n\n"
        f"Transcript:\n{text}"
    )

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        response_format={"type": "json_object"},
    )
    data = json.loads(resp.choices[0].message.content)

    title = (data.get("title") or "").strip()[:MAX_TITLE]
    hashtags = [h if h.startswith("#") else f"#{h}" for h in data.get("hashtags", [])]
    if "#Shorts" not in hashtags:
        hashtags.insert(0, "#Shorts")
    tags = [t.lstrip("#").strip().lower() for t in data.get("tags", []) if t.strip()]

    description = (data.get("description") or "").strip()
    if hashtags:
        description = f"{description}\n\n{' '.join(hashtags)}"
    description = description[:MAX_DESCRIPTION]

    return {
        "title": title or build_title_offline(text, fallback_name),
        "description": description,
        "hashtags": hashtags,
        "tags": tags or build_api_tags(text),
    }


# ----------------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------------
def generate_seo(srt_path, fallback_name=""):
    """Generate SEO from a transcript file, choosing backend via env vars."""
    text = parse_srt(srt_path)
    if not text:
        text = re.sub(r"[_\-]+", " ", fallback_name).strip()

    use_openai = os.environ.get("USE_OPENAI", "").strip() in ("1", "true", "yes")
    if use_openai and os.environ.get("OPENAI_API_KEY"):
        try:
            return generate_openai(text, fallback_name)
        except Exception as e:  # noqa: BLE001 - fall back so uploads never break
            print(f"⚠️ OpenAI SEO failed ({e}); falling back to offline.")

    return generate_offline(text, fallback_name)
