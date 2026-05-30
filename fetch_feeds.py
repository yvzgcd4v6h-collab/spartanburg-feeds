"""
Spartanburg Civic Feed Fetcher
Runs on GitHub Actions, writes results to data/ for Claude to read.
"""

import os
import json
import datetime
import requests
import feedparser
from bs4 import BeautifulSoup

OUTPUT_DIR = "data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

NOW = datetime.datetime.utcnow().isoformat() + "Z"
CUTOFF_DAYS = 35  # fetch posts from the past ~5 weeks


def days_ago(dt):
    """Return how many days ago a datetime was."""
    if isinstance(dt, str):
        try:
            dt = datetime.datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return 999
    if dt.tzinfo:
        dt = dt.replace(tzinfo=None)
    return (datetime.datetime.utcnow() - dt).days


def parse_feed(url, source_name):
    """Fetch and parse an RSS/Atom feed, return list of recent items."""
    print(f"Fetching: {source_name} ({url})")
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; SpartanburgCivicBot/1.0)"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        items = []
        for entry in feed.entries:
            # Parse date
            published = None
            for field in ("published", "updated", "created"):
                if hasattr(entry, field):
                    try:
                        import email.utils
                        t = email.utils.parsedate_to_datetime(getattr(entry, field))
                        published = t.replace(tzinfo=None)
                        break
                    except Exception:
                        pass

            if published and days_ago(published) > CUTOFF_DAYS:
                continue

            # Clean description
            desc = ""
            if hasattr(entry, "summary"):
                soup = BeautifulSoup(entry.summary, "lxml")
                desc = soup.get_text(separator=" ", strip=True)[:500]

            items.append({
                "title": getattr(entry, "title", ""),
                "link": getattr(entry, "link", ""),
                "published": published.isoformat() if published else None,
                "description": desc,
                "source": source_name,
            })

        print(f"  → {len(items)} recent items")
        return items

    except Exception as e:
        print(f"  ERROR: {e}")
        return []


def fetch_folo(token):
    """Fetch recent timeline entries from Folo API."""
    print("Fetching: Folo timeline")
    if not token:
        print("  SKIP: No FOLO_TOKEN set")
        return []
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        resp = requests.get(
            "https://api.folo.is/v1/timeline?limit=50&unread_only=false",
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        entries = data.get("data", {}).get("entries", [])
        items = []
        for e in entries:
            pub = e.get("publishedAt") or e.get("insertedAt")
            if pub and days_ago(pub) > CUTOFF_DAYS:
                continue
            items.append({
                "title": e.get("title", ""),
                "link": e.get("url", ""),
                "published": pub,
                "description": (e.get("description") or "")[:500],
                "source": f"Folo: {e.get('feeds', {}).get('title', 'Unknown')}",
            })
        print(f"  → {len(items)} recent items")
        return items
    except Exception as e:
        print(f"  ERROR: {e}")
        return []


def fetch_urbanplanet():
    """Scrape recent Urban Planet Spartanburg thread activity via Google."""
    print("Fetching: Urban Planet Spartanburg (via Google)")
    # Use SerpAPI if key is available, otherwise skip
    api_key = os.environ.get("SERPAPI_KEY")
    if not api_key:
        print("  SKIP: No SERPAPI_KEY set — trying direct Google scrape")
        return fetch_urbanplanet_direct()

    try:
        params = {
            "engine": "google",
            "q": "site:forum.urbanplanet.org/topic spartanburg",
            "tbs": "qdr:m",  # past month
            "num": 20,
            "api_key": api_key,
        }
        resp = requests.get("https://serpapi.com/search", params=params, timeout=15)
        resp.raise_for_status()
        results = resp.json().get("organic_results", [])
        items = []
        for r in results:
            items.append({
                "title": r.get("title", ""),
                "link": r.get("link", ""),
                "published": None,
                "description": r.get("snippet", "")[:500],
                "source": "Urban Planet Spartanburg",
            })
        print(f"  → {len(items)} results")
        return items
    except Exception as e:
        print(f"  ERROR: {e}")
        return []


def fetch_urbanplanet_direct():
    """Fallback: try fetching Urban Planet RSS directly."""
    urls_to_try = [
        "https://forum.urbanplanet.org/forum/222-spartanburg/?rss=1",
        "https://forum.urbanplanet.org/forum/222-spartanburg/?rss",
        "https://forum.urbanplanet.org/discover/222.xml",
    ]
    for url in urls_to_try:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200 and "xml" in resp.headers.get("content-type", ""):
                feed = feedparser.parse(resp.content)
                if feed.entries:
                    print(f"  → RSS found at {url}: {len(feed.entries)} items")
                    return [{"title": e.title, "link": e.link, "published": None,
                             "description": "", "source": "Urban Planet Spartanburg"}
                            for e in feed.entries]
        except Exception:
            pass
    print("  → No RSS endpoint accessible from GitHub Actions")
    return []


# ── FEED SOURCES ──────────────────────────────────────────────────────────────

RSS_FEEDS = [
    # FetchRSS feeds (replace URLs with your working FetchRSS feed URLs)
    ("https://fetchrss.com/feed/1wMWleAY716S1wMWmGGgs4Hq.rss",
     "Downtown Spartanburg SC (Facebook)"),

    # Add remaining FetchRSS feeds here as you set them up:
    # ("https://fetchrss.com/feed/XXXXXXXX.rss", "City of Spartanburg (Facebook)"),
    # ("https://fetchrss.com/feed/XXXXXXXX.rss", "OneSpartanburg (Facebook)"),
    # ("https://fetchrss.com/feed/XXXXXXXX.rss", "McMillan Pazdan Smith (Facebook)"),
    # ("https://fetchrss.com/feed/XXXXXXXX.rss", "Johnston Design Group (Facebook)"),

    # Direct RSS feeds (no auth needed)
    ("https://www.cityofspartanburg.org/RSSFeed.aspx?ModID=64&CID=All-0",
     "City of Spartanburg News"),
    ("https://www.cityofspartanburg.org/RSSFeed.aspx?ModID=54&CID=All-0",
     "City of Spartanburg Agendas"),

    # Walking Spartan Substack
    ("https://walkingspartan.substack.com/feed",
     "Walking Spartan Substack"),

    # Upstate Business Journal
    ("https://upstatebusinessjournal.com/feed/",
     "Upstate Business Journal"),

    # Post & Courier Spartanburg
    ("https://www.postandcourier.com/spartanburg/local/feed/",
     "Post & Courier Spartanburg"),
]


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    all_items = []

    # RSS feeds
    for url, name in RSS_FEEDS:
        items = parse_feed(url, name)
        all_items.extend(items)

    # Folo timeline
    folo_token = os.environ.get("FOLO_TOKEN", "")
    all_items.extend(fetch_folo(folo_token))

    # Urban Planet
    all_items.extend(fetch_urbanplanet())

    # Sort by date, newest first
    def sort_key(item):
        pub = item.get("published")
        if not pub:
            return ""
        return pub

    all_items.sort(key=sort_key, reverse=True)

    # Write combined output
    output = {
        "generated": NOW,
        "item_count": len(all_items),
        "cutoff_days": CUTOFF_DAYS,
        "items": all_items,
    }

    out_path = os.path.join(OUTPUT_DIR, "feeds.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nWrote {len(all_items)} items to {out_path}")

    # Also write a plain text summary for easy reading
    lines = [f"Spartanburg Civic Feeds — {NOW}\n{'='*60}\n"]
    for item in all_items:
        lines.append(f"[{item['source']}] {item['published'] or 'n/d'}")
        lines.append(f"  {item['title']}")
        if item['description']:
            lines.append(f"  {item['description'][:200]}")
        lines.append(f"  {item['link']}")
        lines.append("")

    txt_path = os.path.join(OUTPUT_DIR, "feeds.txt")
    with open(txt_path, "w") as f:
        f.write("\n".join(lines))
    print(f"Wrote summary to {txt_path}")


if __name__ == "__main__":
    main()
