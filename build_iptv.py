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
    entries = []
    seen_urls = set()
    for stream in streams:
        url = (stream.get("url") or "").strip()
        channel = channels.get(stream.get("channel"))
        if not url.startswith(("https://", "http://")) or not channel:
            continue
        if channel.get("country") not in COUNTRIES or channel.get("is_nsfw"):
            continue
        cats = channel.get("categories") or ["general"]
        category = next((c for c in cats if c in CATEGORIES), None)
        if not category or url in seen_urls:
            continue
        seen_urls.add(url)
        country = channel["country"].upper()
        name = safe(channel.get("name") or stream.get("title") or stream["channel"])
        title = f"{name} [{country}]"
        logo = safe(logos.get(channel["id"], ""))
        group = safe(f"{country} | {LABELS.get(category, category.capitalize())}")
        tvgid = safe(channel["id"])
        entries.append((country, group, name.casefold(), f'#EXTINF:-1 tvg-id="{tvgid}" tvg-logo="{logo}" group-title="{group}",{title}\n{url}'))
    if not entries:
        raise RuntimeError("No channels found. Existing playlist will not be overwritten.")
    entries.sort()
    path = Path("playlist.m3u")
    path.write_text("#EXTM3U\n" + "\n".join(x[3] for x in entries) + "\n", encoding="utf-8")
    print(f"Created {path}: {len(entries)} unique stream URLs")
    print("Note: public listings do not guarantee authorization, availability, or regional access.")
if __name__ == "__main__":
    main()
