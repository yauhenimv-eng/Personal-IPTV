#!/usr/bin/env python3
"""Build an M3U playlist from public IPTV-org metadata (not a stream relay)."""
import json
import os
import subprocess
import time
import concurrent.futures
import urllib.error
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
    # Bounded checks: preserve existing channel URLs when network is inconclusive.
    # Check alternatives first; a temporary failure never removes a channel.
    old = {}
    previous = Path("playlist.m3u")
    if previous.exists():
        lines = previous.read_text(encoding="utf-8-sig").splitlines()
        for i, line in enumerate(lines[:-1]):
            if line.startswith("#EXTINF:") and 'tvg-id="' in line:
                cid = line.split('tvg-id="', 1)[1].split('"', 1)[0]
                old[cid] = lines[i + 1].strip()
    options = {}
    for stream in streams:
        cid, url = stream.get("channel"), (stream.get("url") or "").strip()
        if cid in selected and url.startswith(("http://", "https://")):
            options.setdefault(cid, set()).add(url)
    def probe(url):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Range": "bytes=0-8191"})
            with urllib.request.urlopen(req, timeout=4) as res:
                chunk = res.read(8192)
                mime = res.headers.get("Content-Type", "").lower()
                if not chunk:
                    return "uncertain"
                if b"#EXTM3U" in chunk[:256]:
                    if b"#EXT-X-" in chunk:
                        return "ok"
                    return "uncertain"
                if b"<html" in chunk[:512].lower():
                    return "bad"
                if "video/" in mime or "application/octet-stream" in mime or chunk[0] == 0x47:
                    return "ok"
                return "uncertain"
        except urllib.error.HTTPError as e:
            return "bad" if e.code in (404, 410) else "uncertain"
        except Exception:
            return "uncertain"
    # FFprobe is used for ambiguous HTTP results only, and with a strict timeout.
    def inspect(url):
        state = probe(url)
        if state != "uncertain":
            return state
        try:
            p = subprocess.run(
                ["ffprobe", "-v", "error", "-rw_timeout", "3000000",
                 "-show_entries", "stream=codec_type", "-of", "csv=p=0", url],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=5, text=True)
            if p.returncode == 0 and any(x in p.stdout for x in ("video", "audio")):
                return "ok"
        except (OSError, subprocess.TimeoutExpired):
            pass
        return "uncertain"
    # Keep the daily run bounded and avoid flooding third-party servers.
    # Prefer the existing working selection and probe alternates on demand.
    checked, verified, replaced, uncertain = 0, 0, 0, 0
    deadline = time.monotonic() + int(os.getenv("IPTV_CHECK_BUDGET_SECONDS", "450"))
    max_checks = int(os.getenv("IPTV_MAX_CHECKS", "1200"))
    tasks = []
    for cid, (_, best, channel, category) in selected.items():
        candidates = sorted(options.get(cid, ()), key=lambda u: (
            u != old.get(cid, best), not u.startswith("https://"),
            not u.lower().split("?", 1)[0].endswith(".m3u8"), u))
        tasks.append((cid, candidates[:4]))
    # A bounded worker pool checks the preferred URL; alternative URLs are
    # checked only when the preferred one is definitively bad or inconclusive.
    def choose(item):
        cid, urls = item
        fallback = old.get(cid) if old.get(cid) in options.get(cid, ()) else selected[cid][1]
        if not urls:
            return cid, fallback, "uncertain", 0
        attempts = 0
        for url in urls:
            if time.monotonic() > deadline:
                break
            attempts += 1
            status = inspect(url)
            if status == "ok":
                return cid, url, "ok", attempts
        return cid, fallback, "uncertain", attempts
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        futures = []
        for item in tasks[:max_checks]:
            futures.append(pool.submit(choose, item))
        for future in concurrent.futures.as_completed(futures):
            cid, url, status, count = future.result()
            checked += count
            if status == "ok":
                verified += 1
                if url != selected[cid][1]:
                    replaced += 1
            else:
                uncertain += 1
            rank, _, channel, category = selected[cid]
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
    print(f"Created {path}: {len(entries)} channels; probes={checked}; verified={verified}; replacements={replaced}; inconclusive={uncertain}")
    Path("IPTV_report.txt").write_text(f"Channels: {len(entries)}\nChecks: {checked}\nVerified: {verified}\nAlternatives selected: {replaced}\nInconclusive: {uncertain}\nNote: checks from GitHub may differ from TV playback due to geoblocking.\n", encoding="utf-8")
    print("Note: public listings do not guarantee authorization, availability, or regional access.")
if __name__ == "__main__":
    main()
