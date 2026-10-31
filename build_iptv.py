#!/usr/bin/env python3
"""Build an M3U playlist from public IPTV-org metadata (not a stream relay)."""
import json
import urllib.request
from pathlib import Path

BASE = "https://iptv-org.github.io/api"
COUNTRIES = {"by", "ru", "ua", "gb", "de", "fr", "pl", "it", "es", "pt", "nl", "be", "ch", "at", "cz", "sk", "hu", "ro", "bg", "gr", "se", "no", "dk", "fi", "ie", "ee", "lv", "lt"}
CATEGORIES = {"news", "movies", "sports", "kids", "music", "documentary", "education", "entertainment", "animation", "series", "general", "lifestyle", "culture", "travel", "science", "comedy"}
LABELS = {"news": "Новости", "movies": "Фильмы", "sports": "Спорт", "kids": "Детские", "music": "Музыка", "documentary": "Познавательные", "education": "Познавательные", "science": "Познавательные", "travel": "Познавательные", "entertainment": "Развлекательные", "general": "Общие"}
def fetch(name):
    req = urllib.request.Request(f"{BASE}/{name}.json", headers={"User-Agent": "Personal-IPTV/1.0"})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)
def safe(value):
    return str(value or "").replace('"', "'").replace("\n", " ").replace("\r", " ")
def main():
    streams = fetch("streams")
    channels = {x["id"]: x for x in fetch("channels")}
    logos = {}
    for item in fetch("logos"):
        cid = item.get("channel")
        if cid and item.get("url") and cid not in logos:
            logos[cid] = item["url"]
    print(f"Source: {len(streams)} streams, {len(channels)} channels, {len(logos)} logos")
    # Keep one preferred stream per canonical IPTV-org channel ID.
    # No network probing: preference is based on metadata, not verified playback.
    selected = {}
    candidates = 0
    for stream in streams:
        url = (stream.get("url") or "").strip()
        cid = stream.get("channel")
        channel = channels.get(cid)
        if not url.startswith(("https://", "http://")) or not channel:
            continue
        if str(channel.get("country") or "").lower() not in COUNTRIES or channel.get("is_nsfw"):
            continue
        cats = channel.get("categories") or ["general"]
        category = next((c for c in cats if c in CATEGORIES), None)
        if not category:
            continue
        candidates += 1
        # Prefer secure HLS, then other HLS, then HTTPS, then HTTP.
        # A stable URL tie-breaker prevents random daily playlist churn.
        lower = url.lower().split("?", 1)[0]
        hls = lower.endswith(".m3u8")
        score = (int(url.startswith("https://") and hls),
                 int(hls), int(url.startswith("https://")),
                 int(bool(stream.get("quality"))))
        rank = (score, -len(url))
        previous = selected.get(cid)
        if previous is None or rank > previous[0] or (rank == previous[0] and url < previous[1]):
            selected[cid] = (rank, url, channel, category)
    entries = []
    seen_urls = set()
    for cid, (_, url, channel, category) in selected.items():
        if url in seen_urls:
            continue
        seen_urls.add(url)
        country = str(channel["country"]).upper()
        name = safe(channel.get("name") or cid)
        title = f"{name} [{country}]"
        logo = safe(logos.get(cid, ""))
        group = safe(LABELS.get(category, {
            "series": "Фильмы и сериалы", "animation": "Детские",
            "lifestyle": "Развлекательные", "comedy": "Развлекательные",
            "culture": "Познавательные"
        }.get(category, "Другие")))
        if group == "Фильмы":
            group = "Фильмы и сериалы"
        tvgid = safe(cid)
        entries.append((group, name.casefold(), cid, f'#EXTINF:-1 tvg-id="{tvgid}" tvg-logo="{logo}" group-title="{group}",{title}\n{url}'))
    print(f"Eligible streams: {candidates}; distinct channel IDs: {len(selected)}; output channels: {len(entries)}")
    if not entries:
        raise RuntimeError("No channels found. Existing playlist will not be overwritten.")
    entries.sort()
    path = Path("playlist.m3u")
    path.write_text("#EXTM3U\n" + "\n".join(x[3] for x in entries) + "\n", encoding="utf-8")
    print(f"Created {path}: {len(entries)} channels (one stream per channel ID)")
    print("Note: public listings do not guarantee authorization, availability, or regional access.")
if __name__ == "__main__":
    main()
