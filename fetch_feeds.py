"""
Spartanburg Civic Feed Fetcher
Runs on GitHub Actions weekly, writes results to data/ for Claude to read.
"""

import os
import json
import time
import datetime
import requests
import feedparser
from bs4 import BeautifulSoup

OUTPUT_DIR = "data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

NOW = datetime.datetime.now(datetime.UTC).isoformat()
CUTOFF_DAYS = 35

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def days_ago(dt):
    if isinstance(dt, datetime.datetime):
        if dt.tzinfo:
            dt = dt.replace(tzinfo=None)
        return (datetime.datetime.utcnow() - dt).days
    return 999


# ── URBAN PLANET ─────────────────────────────────────────────────────────────

URBANPLANET_URL = "https://forum.urbanplanet.org/forum/222-spartanburg/"

def fetch_urbanplanet():
    print("Fetching: Urban Planet Spartanburg (subforum scrape)")
    cookie = os.environ.get("URBANPLANET_COOKIE")
    headers = {**HEADERS}
    if cookie:
        headers["Cookie"] = f"ips4_IPSSessionFront={cookie}"
    else:
        print("  NOTE: No URBANPLANET_COOKIE — fetching without auth")

    try:
        resp = requests.get(URBANPLANET_URL, headers=headers, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        items = []

        # Invision Power Board 4.x thread rows
        # Threads are in <li class="ipsDataItem"> elements
        for row in soup.select("li.ipsDataItem, div.ipsDataItem"):

            # Thread title and link
            title_el = (
                row.select_one("span.ipsContained a") or
                row.select_one("h4 a") or
                row.select_one(".ipsDataItem_title a") or
                row.select_one("a[data-ipshover]") or
                row.select_one("a[href*='/topic/']")
            )
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            link = title_el.get("href", "")
            if not link.startswith("http"):
                link = "https://forum.urbanplanet.org" + link

            # Skip non-topic links
            if "/topic/" not in link:
                continue

            # Last activity timestamp
            # Invision uses <time datetime="ISO8601"> for all dates
            time_els = row.select("time[datetime]")
            pub = None
            for t in time_els:
                dt_str = t.get("datetime", "")
                try:
                    pub = datetime.datetime.fromisoformat(
                        dt_str.replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                    break
                except Exception:
                    pass

            # Filter by recency
            if pub and days_ago(pub) > CUTOFF_DAYS:
                continue

            # Last poster
            poster_el = row.select_one(".ipsDataItem_lastPoster a, .ipsType_break a")
            poster = poster_el.get_text(strip=True) if poster_el else ""

            # Reply count
            replies_el = row.select_one(
                ".ipsDataItem_stats_replies, [data-role='replyCount']"
            )
            replies = replies_el.get_text(strip=True) if replies_el else ""

            desc_parts = []
            if poster:
                desc_parts.append(f"Last post by {poster}")
            if replies:
                desc_parts.append(f"{replies} replies")

            items.append({
                "title": title,
                "link": link,
                "published": pub.isoformat() if pub else None,
                "description": " · ".join(desc_parts),
                "source": "Urban Planet Spartanburg",
            })

        if not items:
            # Debug: save a snippet of the HTML to help diagnose selector issues
            snippet = resp.text[:2000]
            print(f"  WARNING: No threads found. HTML snippet:\n{snippet}\n")
        else:
            print(f"  → {len(items)} recently active threads")

        return items

    except Exception as e:
        print(f"  ERROR: {e}")
        return []


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
            options={"allow_extra_requests": False, "posts_per_page": 10},
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


# ── RSS FEEDS ────────────────────────────────────────────────────────────────

RSS_FEEDS = [
    ("https://walkingspartan.substack.com/feed",               "Walking Spartan Substack"),
    ("https://upstatebusinessjournal.com/feed/",               "Upstate Business Journal"),
    ("https://www.postandcourier.com/spartanburg/local/feed/", "Post & Courier Spartanburg"),
    ("https://www.wspa.com/feed/",                             "WSPA 7News"),
    ("https://www.foxcarolina.com/feed/",                      "Fox Carolina"),
]

def parse_feed(url, source_name, retries=3):
    print(f"Fetching RSS: {source_name}")
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
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
            print(f"  attempt {attempt+1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
    print(f"  → 0 items after {retries} attempts")
    return []


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    all_items = []

    # Urban Planet subforum scrape
    all_items.extend(fetch_urbanplanet())

    # Facebook pages
    for page_name, source_name in FACEBOOK_PAGES:
        all_items.extend(scrape_facebook(page_name, source_name))
        time.sleep(2)

    # RSS feeds
    for url, name in RSS_FEEDS:
        all_items.extend(parse_feed(url, name))

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
