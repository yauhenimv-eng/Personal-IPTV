#!/usr/bin/env python3
"""Build a small XMLTV guide containing only channels in our playlist."""
import gzip
import io
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

# Public country XMLTV guides. Unavailable countries simply remain unmatched.
COUNTRIES = ("by", "ru", "ua", "gb", "pl", "de", "fr", "it", "es", "nl", "cz", "ro")
BASE = "https://iptv-epg.org/files/epg-{}.xml"
ATTR = re.compile(r'tvg-id="([^"]+)"')
MAX_BYTES = 250_000_000

def main():
    playlist = Path("playlist.m3u").read_text(encoding="utf-8-sig")
    wanted = set(ATTR.findall(playlist))
    if not wanted:
        raise RuntimeError("No tvg-id entries in playlist")
    root = ET.Element("tv")
    found = set()
    programmes = 0
    sources_ok = 0
    for country in COUNTRIES:
        url = BASE.format(country)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Personal-IPTV/EPG"})
            with urllib.request.urlopen(req, timeout=55) as response:
                payload = response.read(MAX_BYTES + 1)
            if len(payload) > MAX_BYTES:
                raise ValueError("XMLTV source exceeds size limit")
            if payload[:2] == b"\x1f\x8b":
                payload = gzip.decompress(payload)
            document = ET.fromstring(payload)
            if document.tag != "tv":
                raise ValueError("Not an XMLTV document")
            sources_ok += 1
            channels = [node for node in document.findall("channel") if node.get("id") in wanted]
            ids = {node.get("id") for node in channels}
            for node in channels:
                if node.get("id") not in found:
                    root.append(node)
                    found.add(node.get("id"))
            for node in document.findall("programme"):
                if node.get("channel") in ids:
                    root.append(node)
                    programmes += 1
            print(f"EPG {country}: {len(ids)} matched channels")
        except Exception as exc:
            print(f"WARNING EPG {country}: {exc}")
    if not found or not programmes:
        # Never overwrite a previously useful guide with an empty one.
        if Path("epg.xml").exists():
            print("WARNING: no fresh EPG matches; keeping previous epg.xml")
            return
        raise RuntimeError("No usable EPG data; check XMLTV providers")
    ET.ElementTree(root).write("epg.xml", encoding="utf-8", xml_declaration=True)
    with Path("IPTV_report.txt").open("a", encoding="utf-8") as report:
        report.write(f"EPG sources available: {sources_ok}\n")
        report.write(f"EPG matched channel IDs: {len(found)}\n")
        report.write(f"EPG programme entries: {programmes}\n")
        report.write(f"EPG coverage percent: {100*len(found)/len(wanted):.1f}\n")
    print(f"EPG: {len(found)} matched channels, {programmes} programmes")

if __name__ == "__main__":
    main()
