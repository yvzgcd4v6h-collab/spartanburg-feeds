# Spartanburg Civic Feeds

Automated feed aggregator for the Spartanburg civic intelligence digest. Runs weekly on GitHub Actions and writes results to `data/feeds.json` and `data/feeds.txt` for Claude to read at digest time.

## Setup

### 1. Create the repo
Create a new GitHub repo (can be private) and push this folder to it.

### 2. Add secrets
In your repo → **Settings → Secrets and variables → Actions**, add:

| Secret | Value | Required? |
|--------|-------|-----------|
| `FOLO_TOKEN` | Your Folo session token | Optional — enables Folo timeline |
| `SERPAPI_KEY` | SerpAPI key (free tier: 100 searches/month) | Optional — enables Urban Planet search |

### 3. Add remaining FetchRSS feed URLs
In `fetch_feeds.py`, find the `RSS_FEEDS` list and uncomment/add your FetchRSS feed URLs for:
- City of Spartanburg (Facebook)
- OneSpartanburg (Facebook)
- McMillan Pazdan Smith (Facebook)
- Johnston Design Group (Facebook)
- SeamonWhiteside (Instagram)

### 4. Enable Actions
Go to **Actions** tab in your repo and enable workflows.

### 5. Run manually first
Trigger the workflow manually via **Actions → Fetch Spartanburg Civic Feeds → Run workflow** to verify it works.

## Usage with Claude

At the start of each monthly digest session, paste this URL into the conversation:

```
https://raw.githubusercontent.com/YOUR_USERNAME/spartanburg-feeds/main/data/feeds.txt
```

Claude will fetch it directly and use it as source material for the digest.

## Schedule
Runs every Monday at 6am ET. Can also be triggered manually via the Actions tab.

## Sources included

### Always on (no auth needed)
- City of Spartanburg News RSS
- City of Spartanburg Agendas RSS
- Walking Spartan Substack
- Upstate Business Journal
- Post & Courier Spartanburg

### FetchRSS feeds (add your URLs)
- Downtown Spartanburg SC (Facebook)
- City of Spartanburg (Facebook)
- OneSpartanburg (Facebook)
- McMillan Pazdan Smith (Facebook)
- Johnston Design Group (Facebook)
- SeamonWhiteside (Instagram)

### Optional (requires secrets)
- Folo timeline (requires `FOLO_TOKEN`)
- Urban Planet Spartanburg via SerpAPI (requires `SERPAPI_KEY`)

## Output
- `data/feeds.json` — full structured data
- `data/feeds.txt` — plain text summary, easiest for Claude to read
