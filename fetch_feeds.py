"""
Spartanburg Civic Feed Fetcher
Runs on GitHub Actions weekly, writes results to data/ for Claude to read.
Replaces FetchRSS with direct scraping via facebook-scraper and instaloader.
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
CUTOFF_DAYS = 35


def days_ago(dt):
    if isinstance(dt, datetime.datetime):
        if dt.tzinfo:
            dt = dt.replace(tzinfo=None)
        return (datetime.datetime.utcnow() - dt).days
    return 999


# ── FACEBOOK ─────────────────────────────────────────────────────────────────

FACEBOOK_PAGES = [
    ("downtownspartanburgsc",   "Downtown Spartanburg SC"),
    ("CityofSpartanburgSC",     "City of Spartanburg"),
    ("OneSpartanburgInc",       "OneSpartanburg, Inc."),
    ("mpsarchitecture",         "McMillan Pazdan Smith"),
    ("johnstondesigngroup",     "Johnston Design Group"),
]

def scrape_facebook(page_name, source_name, pages=2):
    print(f"Fetching Facebook: {source_name} (@{page_name})")
    try:
        from facebook_scraper import get_posts
        items = []
        for post in get_posts(
            page_name,
            pages=pages,
            options={
                "allow_extra_requests": False,
                "posts_per_page": 10,
            },
        ):
            pub = post.get("time")
            if pub and days_ago(pub) > CUTOFF_DAYS:
                continue
            text = (post.get("text") or post.get("post_text") or "").strip()
            if not text:
                continue
            items.append({
                "title": text[:120] + ("..." if len(text) > 120 else ""),
                "link": post.get("post_url") or f"https://www.facebook.com/{page_name}",
                "published": pub.isoformat() if pub else None,
                "description": text[:500],
                "source": source_name,
            })
        print(f"  → {len(items)} items")
        return items
    except Exception as e:
        print(f"  ERROR: {e}")
        return []


# ── INSTAGRAM ────────────────────────────────────────────────────────────────

INSTAGRAM_ACCOUNTS = [
    ("seamonwhiteside",     "SeamonWhiteside"),
    ("studioteague",        "Teague Studio"),
    ("mpsarchitecture",     "McMillan Pazdan Smith (Instagram)"),
]

def scrape_instagram(username, source_name, limit=10):
    print(f"Fetching Instagram: {source_name} (@{username})")
    try:
        import instaloader
        L = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            compress_json=False,
            save_metadata=False,
            quiet=True,
        )
        profile = instaloader.Profile.from_username(L.context, username)
        items = []
        for post in profile.get_posts():
            if len(items) >= limit:
                break
            if days_ago(post.date_utc) > CUTOFF_DAYS:
                continue
            caption = (post.caption or "").strip()
            items.append({
                "title": caption[:120] + ("..." if len(caption) > 120 else ""),
                "link": f"https://www.instagram.com/p/{post.shortcode}/",
                "published": post.date_utc.isoformat(),
                "description": caption[:500],
                "source": source_name,
            })
        print(f"  → {len(items)} items")
        return items
    except Exception as e:
        print(f"  ERROR: {e}")
        return []


# ── RSS FEEDS ────────────────────────────────────────────────────────────────

RSS_FEEDS = [
    ("https://walkingspartan.substack.com/feed",
     "Walking Spartan Substack"),
    ("https://upstatebusinessjournal.com/feed/",
     "Upstate Business Journal"),
    ("https://www.postandcourier.com/spartanburg/local/feed/",
     "Post & Courier Spartanburg"),
    ("https://www.wspa.com/feed/",
     "WSPA 7News"),
]

def parse_feed(url, source_name):
    print(f"Fetching RSS: {source_name}")
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; SpartanburgCivicBot/1.0)"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        items = []
        for entry in feed.entries:
            pub = None
            for field in ("published", "updated", "created"):
                val = getattr(entry, field, None)
                if val:
                    try:
                        import email.utils
                        pub = email.utils.parsedate_to_datetime(val).replace(tzinfo=None)
                        break
                    except Exception:
                        pass
            if pub and days_ago(pub) > CUTOFF_DAYS:
                continue
            desc = ""
            if hasattr(entry, "summary"):
                desc = BeautifulSoup(entry.summary, "lxml").get_text(" ", strip=True)[:500]
            items.append({
                "title": getattr(entry, "title", ""),
                "link": getattr(entry, "link", ""),
                "published": pub.isoformat() if pub else None,
                "description": desc,
                "source": source_name,
            })
        print(f"  → {len(items)} items")
        return items
    except Exception as e:
        print(f"  ERROR: {e}")
        return []


# ── URBAN PLANET ─────────────────────────────────────────────────────────────

def fetch_urbanplanet():
    print("Fetching: Urban Planet Spartanburg (Google search)")
    api_key = os.environ.get("SERPAPI_KEY")
    items = []
    try:
        if api_key:
            params = {
                "engine": "google",
                "q": "site:forum.urbanplanet.org spartanburg",
                "tbs": "qdr:m",
                "num": 20,
                "api_key": api_key,
            }
            resp = requests.get("https://serpapi.com/search", params=params, timeout=15)
            results = resp.json().get("organic_results", [])
            for r in results:
                items.append({
                    "title": r.get("title", ""),
                    "link": r.get("link", ""),
                    "published": None,
                    "description": r.get("snippet", "")[:500],
                    "source": "Urban Planet Spartanburg",
                })
        else:
            # Direct Google scrape fallback
            headers = {"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1)"}
            resp = requests.get(
                "https://www.google.com/search?q=site:forum.urbanplanet.org+spartanburg&tbs=qdr:m&num=20",
                headers=headers, timeout=15
            )
            soup = BeautifulSoup(resp.text, "lxml")
            for result in soup.select("div.g")[:20]:
                title_el = result.select_one("h3")
                link_el = result.select_one("a")
                desc_el = result.select_one("div.VwiC3b, span.st")
                if title_el and link_el:
                    href = link_el.get("href", "")
                    if "urbanplanet.org" in href:
                        items.append({
                            "title": title_el.get_text(strip=True),
                            "link": href,
                            "published": None,
                            "description": desc_el.get_text(strip=True)[:500] if desc_el else "",
                            "source": "Urban Planet Spartanburg",
                        })
    except Exception as e:
        print(f"  ERROR: {e}")
    print(f"  → {len(items)} items")
    return items


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    all_items = []

    # Facebook pages
    for page_name, source_name in FACEBOOK_PAGES:
        all_items.extend(scrape_facebook(page_name, source_name))

    # Instagram accounts
    for username, source_name in INSTAGRAM_ACCOUNTS:
        all_items.extend(scrape_instagram(username, source_name))

    # RSS feeds
    for url, name in RSS_FEEDS:
        all_items.extend(parse_feed(url, name))

    # Urban Planet
    all_items.extend(fetch_urbanplanet())

    # Sort newest first
    all_items.sort(key=lambda x: x.get("published") or "", reverse=True)

    # Write JSON
    output = {
        "generated": NOW,
        "item_count": len(all_items),
        "cutoff_days": CUTOFF_DAYS,
        "items": all_items,
    }
    with open(f"{OUTPUT_DIR}/feeds.json", "w") as f:
        json.dump(output, f, indent=2)

    # Write plain text summary
    lines = [f"Spartanburg Civic Feeds — {NOW}", "=" * 60, ""]
    for item in all_items:
        lines.append(f"[{item['source']}] {item['published'] or 'n/d'}")
        lines.append(f"  {item['title']}")
        if item["description"] and item["description"] != item["title"]:
            lines.append(f"  {item['description'][:200]}")
        lines.append(f"  {item['link']}")
        lines.append("")
    with open(f"{OUTPUT_DIR}/feeds.txt", "w") as f:
        f.write("\n".join(lines))

    print(f"\nDone — {len(all_items)} total items written to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
