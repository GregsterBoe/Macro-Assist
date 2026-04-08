"""
youtube_data.py — Fetch recent video transcripts from YouTube channels via Supadata.

Requires SUPADATA_API_KEY environment variable / GitHub secret.
Sign up: https://supadata.ai (free tier: 100 requests/month)

Finding a channel ID
--------------------
The RSS feed requires a channel ID (format: UC...), not a display name.
Find it by opening the channel page, viewing page source, and searching
for "channelId" — it appears as: "channelId":"UCxxxxxxxxxxxxxxxxxxxx"
"""

import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LOOKBACK_HOURS   = 36   # catch weekend gaps on Monday runs
SUPADATA_API_KEY = os.environ.get("SUPADATA_API_KEY")
SUPADATA_URL     = "https://api.supadata.ai/v1/youtube/transcript"
RSS_URL          = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt":   "http://www.youtube.com/xml/schemas/2015",
}


# ---------------------------------------------------------------------------
# RSS — list recent videos (no auth required)
# ---------------------------------------------------------------------------

def fetch_recent_videos(channel_id: str) -> list[dict]:
    """
    Return videos published in the last LOOKBACK_HOURS from the channel RSS.
    Each entry: {video_id, title, published}
    """
    url = RSS_URL.format(channel_id=channel_id)
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except Exception as exc:
        print(f"  Warning: RSS fetch failed for {channel_id}: {exc}", file=sys.stderr)
        return []

    root   = ET.fromstring(resp.content)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    recent = []

    for entry in root.findall("atom:entry", NS):
        pub_el = entry.find("atom:published", NS)
        if pub_el is None:
            continue
        published = datetime.fromisoformat(pub_el.text.replace("Z", "+00:00"))
        if published < cutoff:
            continue

        vid_el   = entry.find("yt:videoId", NS)
        title_el = entry.find("atom:title", NS)
        if vid_el is None or title_el is None:
            continue

        recent.append({
            "video_id":  vid_el.text,
            "title":     title_el.text,
            "published": published.isoformat(),
            "url":       f"https://www.youtube.com/watch?v={vid_el.text}",
        })

    return recent


# ---------------------------------------------------------------------------
# Supadata — fetch full transcript
# ---------------------------------------------------------------------------

def fetch_transcript(video_id: str) -> str | None:
    """
    Fetch the full transcript for a video via Supadata.
    Returns plain text or None if unavailable.
    """
    if not SUPADATA_API_KEY:
        print("  Warning: SUPADATA_API_KEY not set — skipping transcript fetch.", file=sys.stderr)
        return None

    try:
        resp = requests.get(
            SUPADATA_URL,
            params={"videoId": video_id, "text": "true"},
            headers={"x-api-key": SUPADATA_API_KEY},
            timeout=20,
        )
        if resp.status_code == 404:
            return None  # no transcript for this video
        resp.raise_for_status()
        return resp.json().get("content") or None
    except Exception as exc:
        print(f"  Warning: Supadata fetch failed for {video_id}: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def get_recent_transcripts(channel_id: str) -> list[dict]:
    """
    Return a list of recent videos with their raw transcripts.
    Each entry: {video_id, title, published, url, transcript}
    Videos with no transcript are excluded.
    """
    videos = fetch_recent_videos(channel_id)
    results = []
    for video in videos:
        transcript = fetch_transcript(video["video_id"])
        if transcript:
            results.append({**video, "transcript": transcript})
    return results
