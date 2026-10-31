# Personal IPTV

Public IPTV playlist compiled from [IPTV-org](https://github.com/iptv-org/iptv) listings for Belarus, Russia, Ukraine and selected European countries.

**TV / IPTV player URL:** https://raw.githubusercontent.com/yauhenimv-eng/Personal-IPTV/main/playlist.m3u

## Update
Run the **Update IPTV playlist** workflow under **Actions** using **Run workflow**. The daily schedule will also refresh the file when source listings change.

The playlist is a collection of third-party stream links, not a video hosting service. Listing a stream does not establish broadcasting rights; verify the stream's permissions and regional availability before using it. IPTV-org identifiers are included for potential EPG matching, but no working EPG feed is guaranteed.

## Local build
```bash
python build_iptv.py
```
