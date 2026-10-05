"""Build a once-a-day digest feed: don't miss what matters, skip the small stuff. Original text, no AI.

Usage:
  uv run digest.py            fetch today's news, save data/YYYY-MM-DD.json, write public/digest.xml and index.html
  uv run digest.py --render   only re-render public/ from the saved data/ (no network) — for tweaking the format
  uv run digest.py --preview  fetch today's news and write public/, but don't save data/ (nothing to commit)
Add --open to open public/index.html in the browser afterwards.
"""

import calendar
import html
import json
import re
import ssl
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

import feedparser

ROOT = Path(__file__).parent
DATA = ROOT / "data"
PUBLIC = ROOT / "public"
CONFIG = tomllib.loads((ROOT / "config.toml").read_text())
TZ = ZoneInfo(CONFIG["timezone"])
WINDOW = timedelta(hours=36)  # a little over a day, so a late run doesn't miss anything; repeats are filtered by `seen`

# 公視 and 中央氣象署 serve certificates that fail Python 3.13's strict X.509 check
# ("Missing Subject Key Identifier"). Keep verification on, just drop the strict flag.
SSL_CTX = ssl.create_default_context()
SSL_CTX.verify_flags &= ~ssl.VERIFY_X509_STRICT

AI_WORDS = re.compile(
    r"\b(AI|A\.I\.|AGI|LLMs?|GPT[-\w]*|ChatGPT|OpenAI|Anthropic|Claude|Gemini|DeepMind|Llama|Mistral|"
    r"Copilot|Apple Intelligence|machine learning|neural|transformers?|chatbots?|inference|agentic)\b",
    re.I,
)


_cache = {}


FAILURES = []


def warn(source, ex):
    """A source failed. Print it, and list it at the bottom of the day's post so a silent day isn't mistaken for a quiet one."""
    print(f"! {source}: {ex}", file=sys.stderr)
    if source not in FAILURES:
        FAILURES.append(source)


def get(url):
    """Fetch a URL; responses are cached because several sections read the same pages."""
    if url in _cache:
        return _cache[url]
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (news-digest; personal RSS reader)"})
    for attempt in range(3):  # sites occasionally answer 5xx or time out; try again before giving up
        try:
            with urllib.request.urlopen(req, timeout=20, context=SSL_CTX) as r:
                body = r.read()
            break
        except urllib.error.HTTPError as ex:
            if ex.code < 500 or attempt == 2:
                raise
        except urllib.error.URLError:
            if attempt == 2:
                raise
        time.sleep(5 * (attempt + 1))
    _cache[url] = body
    return body


def clean(text, limit=None):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:!?)])", r"\1", text)  # removing tags can leave "league ," behind
    limit = limit or CONFIG["summary_chars"]
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def entry_time(e):
    t = e.get("published_parsed") or e.get("updated_parsed")
    return datetime.fromtimestamp(calendar.timegm(t), timezone.utc) if t else None


def page_description(url):
    """The article's own <meta description>, used when the source gives no summary."""
    try:
        page = get(url).decode("utf-8", "replace")
    except Exception:
        return ""
    for pattern in (r'<meta[^>]+property="og:description"[^>]+content="([^"]*)"',
                    r'<meta[^>]+name="description"[^>]+content="([^"]*)"'):
        if m := re.search(pattern, page):
            return clean(m.group(1))
    return ""


def article(title, link, source, summary=None, score=None):
    return {"title": clean(title, 300), "link": link, "source": source, "score": score,
            "summary": clean(summary) if summary is not None else page_description(link)}


# --- headline pickers: each yields candidate articles, most important first ---

def rss_first(src, now):
    """Feeds ordered by editorial importance (e.g. BBC), not by time."""
    for e in feedparser.parse(get(src["url"])).entries:
        t = entry_time(e)
        if t and t >= now - WINDOW:
            yield article(e.title, e.link, src["name"], e.get("summary", ""))


def cna_home(src, now):
    """The big top story on cna.com.tw (<a class="majorNewsClick"> wrapping <h2 class="biggest">)."""
    page = get(src["url"]).decode("utf-8", "replace")
    m = re.search(r'<a class="majorNewsClick" href="([^"]+)">(?:(?!</a>).)*?<h2 class="biggest">([^<]+)</h2>', page, re.S)
    if m:
        yield article(m.group(2), urllib.parse.urljoin(src["url"], m.group(1)), src["name"])


def hn_top(src, now):
    """Highest-scoring Hacker News story in the window: AI-related only, unless `any_topic` is set."""
    query = urllib.parse.urlencode({
        "tags": "story", "hitsPerPage": 500,
        "numericFilters": f"created_at_i>{int((now - WINDOW).timestamp())},points>30",
    })
    hits = json.loads(get(f"https://hn.algolia.com/api/v1/search_by_date?{query}"))["hits"]
    for h in sorted(hits, key=lambda h: -h["points"]):
        if src.get("any_topic") or AI_WORDS.search(h["title"]):
            discussion = f"https://news.ycombinator.com/item?id={h['objectID']}"
            yield article(h["title"], h.get("url") or discussion, f"{src['name']} · {h['points']} points",
                          score=h["points"])


def itn_html():
    return json.loads(get("https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "parse", "page": "Template:In_the_news", "prop": "text", "format": "json", "formatversion": 2,
    })))["parse"]["text"]


def wikipedia_itn(src, now):
    """Stories in the "In the news" box on English Wikipedia's main page, top first."""
    text = itn_html()
    box = re.search(r"<ul>(.*?)</ul>", text, re.S)
    for li in re.findall(r"<li>(.*?)</li>", box.group(1) if box else "", re.S):
        main = re.search(r'<b>\s*<a href="(/wiki/[^"#]+)"', li) or re.search(r'<a href="(/wiki/[^"#]+)"', li)
        title = re.sub(r"\s*\(pictured\)", "", clean(li, 300))
        if main and not re.match(r"In [a-z][\w -]*,", title):  # sports results read "In rugby league, ..."
            yield article(title, f"https://en.wikipedia.org{main.group(1)}", src["name"], "")


def alphaxiv(src, now):
    """Most-liked papers on alphaXiv over the past week."""
    query = urllib.parse.urlencode({"pageNum": 0, "pageSize": 20, "sort": "Likes", "interval": "7 Days"})
    for p in json.loads(get(f"https://api.alphaxiv.org/papers/v3/feed?{query}"))["papers"]:
        votes = (p.get("metrics") or {}).get("public_total_votes") or 0
        yield article(p["title"], f"https://www.alphaxiv.org/abs/{p['universal_paper_id']}",
                      f"{src['name']} · {votes} likes", p.get("abstract", ""), score=votes)


def hf_papers(src, now):
    """Most-upvoted paper from two days ago, so the upvotes have had time to settle."""
    day = (now - timedelta(days=2)).date().isoformat()
    papers = json.loads(get(f"https://huggingface.co/api/daily_papers?date={day}"))
    for p in sorted(papers, key=lambda p: -p["paper"].get("upvotes", 0)):
        votes = p["paper"].get("upvotes", 0)
        yield article(p["title"], f"https://huggingface.co/papers/{p['paper']['id']}",
                      f"{src['name']} · {votes} upvotes", p["paper"].get("summary", ""), score=votes)


def github_trending(src, now):
    page = get("https://github.com/trending?since=daily").decode("utf-8", "replace")
    for row in page.split('<article class="Box-row">')[1:]:
        name = re.search(r'<h2[^>]*>\s*<a[^>]*href="/([^"]+)"', row)
        stars = re.search(r"([\d,]+)\s+stars today", row)
        desc = re.search(r'<p class="[^"]*">\s*(.*?)\s*</p>', row, re.S)
        if name and stars:
            n = int(stars.group(1).replace(",", ""))
            yield article(name.group(1), f"https://github.com/{name.group(1)}",
                          f"{src['name']} · {n:,} stars today", desc.group(1) if desc else "", score=n)


PICKERS = {"rss_first": rss_first, "cna_home": cna_home, "wikipedia_itn": wikipedia_itn, "hn_top": hn_top,
           "alphaxiv": alphaxiv, "hf_papers": hf_papers, "github_trending": github_trending}


def headlines(category, now, seen, scores):
    """Without `each`: the first source that has a new article wins.
    With `each`: every source contributes its top new article if it clears `min`."""
    picked = []
    for src in category["sources"]:
        try:
            top = next((a for a in PICKERS[src["method"]](src, now) if a["link"] not in seen), None)
        except Exception as ex:
            warn(f"{src['name']}", ex)
            continue
        if top is None:
            continue
        if top["score"] is not None:
            scores[src["name"]] = top["score"]
        if top["score"] is None or top["score"] >= src.get("min", 0):
            picked.append(top)
            seen.add(top["link"])
            if not category.get("each"):
                break
    return picked


# --- sections that only show up when something happens ---

def alerts(now, seen):
    cfg, items = CONFIG["alerts"], []
    # 中央氣象署: titles exactly as published, with links back (required by their terms).
    # Typhoon warnings are reissued every few hours, so keep only the latest one per keyword.
    try:
        entries = feedparser.parse(get(cfg["cwa_warnings"])).entries
        for kw in cfg["warning_keywords"]:
            hits = [e for e in entries if kw in e.title and e.link not in seen
                    and (entry_time(e) or now) >= now - WINDOW]
            if hits:
                e = max(hits, key=lambda e: entry_time(e) or now)
                items.append({"title": e.title.strip(), "link": e.link, "source": "中央氣象署"})
    except Exception as ex:
        warn(f"中央氣象署", ex)

    box = cfg["quake_box"]
    query = urllib.parse.urlencode({
        "format": "geojson", "starttime": (now - WINDOW).astimezone(timezone.utc).isoformat(timespec="seconds"),
        "minmagnitude": cfg["quake_min"], "minlatitude": box["min_lat"], "maxlatitude": box["max_lat"],
        "minlongitude": box["min_lon"], "maxlongitude": box["max_lon"],
    })
    try:
        for f in json.loads(get(f"https://earthquake.usgs.gov/fdsnws/event/1/query?{query}"))["features"]:
            p = f["properties"]
            if p["url"] in seen:
                continue
            t = datetime.fromtimestamp(p["time"] / 1000, TZ)
            items.append({"title": f"規模 {p['mag']} 地震 {t:%m/%d %H:%M}（{p['place']}）",
                          "link": p["url"], "source": "USGS"})
    except Exception as ex:
        warn(f"USGS", ex)
    return items


def nuxt_state(page, keys):
    """Decode Nuxt's __NUXT_DATA__ payload (a flat array where objects point at other entries by index)."""
    raw = re.search(r'<script type="application/json"[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    arr = json.loads(raw.group(1))

    def resolve(i):
        v = arr[i]
        if isinstance(v, list):
            if v and isinstance(v[0], str):  # tagged value such as ["Reactive", 12] or ["Date", "..."]
                return resolve(v[1]) if len(v) > 1 and isinstance(v[1], int) else None
            return [resolve(x) for x in v]
        if isinstance(v, dict):
            return {k: resolve(x) for k, x in v.items()}
        return v

    return [resolve(i) for i, v in enumerate(arr) if isinstance(v, dict) and keys & v.keys()]


def civic(now, seen):
    """中選會: upcoming votes (countdown) and new announcements about elections, referendums, recalls."""
    cfg, items = CONFIG["civic"], []
    try:
        objs = nuxt_state(get(cfg["url"]).decode("utf-8", "replace"), {"calendarList", "bulletinList"})
    except Exception as ex:
        warn(f"中選會", ex)
        return items

    for obj in objs:
        for ev in obj.get("calendarList") or []:
            d = datetime.strptime(ev["date"], "%Y%m%d").date()
            left = (d - now.date()).days
            if 0 <= left <= cfg["countdown_days"]:
                when = "今天" if left == 0 else f"還有 {left} 天"
                items.append({"title": f"📅 {ev['title']}：{d.month}/{d.day}（{when}）",
                              "link": cfg["url"], "source": "中選會行事曆"})

    titles = set()
    for obj in objs:
        for group in obj.get("bulletinList") or []:
            for a in group.get("articleList") or []:
                # The site builds article URLs in JavaScript, so link to the homepage where the list lives;
                # the fragment just makes each announcement a distinct key for `seen`.
                key = f"{cfg['url']}#article-{a['articleId']}"
                t = datetime.strptime(a["beginTime"], "%Y%m%d%H%M%S").replace(tzinfo=TZ)
                if (t < now - WINDOW or key in seen or a["title"] in titles
                        or not any(k in a["title"] for k in cfg["keywords"])
                        or any(k in a["title"] for k in cfg["exclude"])):
                    continue
                titles.add(a["title"])
                items.append({"title": a["title"], "link": key, "source": f"中選會{group['name']}"})
    return items


STOPWORDS = {"after", "with", "from", "that", "this", "have", "into", "over", "says", "said", "about", "their",
             "what", "watch", "will", "been", "more", "than", "were", "when", "how"}


def tokens(text):
    words = {w for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in STOPWORDS}
    cjk = re.sub(r"[^\u4e00-\u9fff]", "", text)
    return words | {cjk[i:i + 2] for i in range(len(cjk) - 1)}


def similar(a, b):
    """Rough same-story check: enough shared words (or Chinese character pairs) between two headlines."""
    ta, tb = tokens(a), tokens(b)
    common = ta & tb
    return len(common) >= 3 and len(common) >= 0.25 * min(len(ta), len(tb))


def watch(now, seen, known, shown_titles):
    """Keyword rules over the pool's recent headlines. A topic switches itself on when at least `min_hits`
    articles match and off when coverage dies down. Returns (chips, one new article per topic, hit counts).
    The article shown for a topic skips stories already on the page (e.g. the world headline)."""
    pool = []
    for src in CONFIG["tracking"]["pool"]:
        try:
            entries = feedparser.parse(get(src["url"])).entries
        except Exception as ex:
            warn(f"{src['name']}", ex)
            continue
        pool += [(src["name"], e) for e in entries if (entry_time(e) or now) >= now - WINDOW]

    chips, items, counts = [], [], {}
    for rule in CONFIG.get("watch", []):
        match = re.compile(rule["match"], re.I)
        require = re.compile(rule["require"], re.I) if rule.get("require") else None
        exclude = re.compile(rule["exclude"], re.I) if rule.get("exclude") else None
        topics = {}  # name -> matching (source, entry), in pool order
        for source, e in pool:
            m = match.search(e.title)
            if m and (not require or require.search(e.title)) and not (exclude and exclude.search(e.title)):
                topics.setdefault(rule["name"].format(*m.groups()), []).append((source, e))
        for name, hits in topics.items():
            counts[name] = len(hits)
            # Skip quiet topics, and ones already covered by a CNA topic or Wikipedia (e.g. 亞運 vs 2026亞運).
            if len(hits) < rule.get("min_hits", 2) or any(name in k or k in name for k in known):
                continue
            known.add(name)
            chips.append({"name": name, "link": hits[0][1].link})
            for source, e in hits:
                if e.link not in seen and not any(similar(e.title, t) for t in shown_titles):
                    items.append({"topic": name, "title": clean(e.title, 300), "link": e.link, "source": source})
                    seen.add(e.link)
                    shown_titles.append(e.title)
                    break
    return chips, items, counts


def wikipedia_ongoing():
    """The "Ongoing" line of English Wikipedia's In the news box, named by the Chinese article when there is one."""
    api = "https://en.wikipedia.org/w/api.php?"
    text = itn_html()
    i = text.find("Ongoing")
    if i < 0:
        return []
    segment = text[i:text.find("</div>", i)]
    titles = [urllib.parse.unquote(href).replace("_", " ")
              for href, label in re.findall(r'<a href="/wiki/([^"#]+)"[^>]*>([^<]+)</a>', segment)
              if not href.startswith("Timeline")]
    if not titles:
        return []
    pages = json.loads(get(api + urllib.parse.urlencode({
        "action": "query", "titles": "|".join(titles), "prop": "langlinks", "lllang": "zh",
        "format": "json", "formatversion": 2,
    })))["query"]["pages"]
    zh = {p["title"]: (p.get("langlinks") or [{}])[0].get("title") for p in pages}
    chips = []
    for t in titles:
        if zh.get(t):
            chips.append({"name": re.sub(r"\s*\(.*?\)$", "", zh[t]),
                          "link": f"https://zh.wikipedia.org/zh-tw/{urllib.parse.quote(zh[t])}"})
        else:
            chips.append({"name": t, "link": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(t.replace(' ', '_'))}"})
    return chips


def hot(now, seen):
    """Keywords for what is going on right now, plus a new article from each CNA topic for tracking."""
    cfg, chips, tracked = CONFIG["hot"], [], []
    try:
        for e in feedparser.parse(get(CONFIG["alerts"]["cwa_warnings"])).entries:
            if "颱風" in e.title:
                m = re.search(r"(?:輕度|中度|強烈)颱風\s*([\u4e00-\u9fff]{2,4})", e.title)
                chips.append({"name": f"颱風{m.group(1)}" if m else "颱風", "link": e.link})
            elif "低溫" in e.title:
                chips.append({"name": "寒流", "link": e.link})
    except Exception as ex:
        warn(f"中央氣象署", ex)

    try:
        chips += wikipedia_ongoing()
    except Exception as ex:
        warn(f"Wikipedia", ex)

    try:
        page = get(cfg["cna_url"]).decode("utf-8", "replace")
        for m in re.finditer(r'<a class="first-level" href="(/topic/newstopic/\d+\.aspx)">([^<]+)</a>(.*?)</ul>', page, re.S):
            name = m.group(2).strip()
            if name in cfg["cna_exclude"]:
                continue
            chips.append({"name": name, "link": urllib.parse.urljoin(cfg["cna_url"], m.group(1))})
            if not cfg.get("track_cna_topics"):
                continue
            for href, title in re.findall(r'<a class="_ellipsis_simple" href="([^"]+)">([^<]+)</a>', m.group(3)):
                link = urllib.parse.urljoin(cfg["cna_url"], href)
                if link not in seen:
                    tracked.append({"topic": name, "title": clean(title, 300), "link": link, "source": "中央社專題"})
                    seen.add(link)
                    break
    except Exception as ex:
        warn(f"中央社專題", ex)

    names = set()
    chips = [c for c in chips if not (c["name"] in names or names.add(c["name"]))]
    return chips, tracked


# --- output ---

def seen_links(today):
    links = set()
    for p in DATA.glob("*.json"):
        if p.stem == today:
            continue
        day = json.loads(p.read_text())
        links.update(a["link"] for a in day["alerts"] + day["civic"] + day.get("tracking", []))
        links.update(a["link"] for cat in day["headlines"] for a in cat["articles"])
    return links


def render(day):
    d = date.fromisoformat(day["date"])

    def link_list(items):
        return "<ul>" + "".join(f'<li><a href="{escape(i["link"])}">{escape(i["title"])}</a> '
                                f'<small>— {escape(i["source"])}</small></li>' for i in items) + "</ul>"

    parts = []
    if day.get("hot"):
        chips = " · ".join(f'<a href="{escape(c["link"])}">{escape(c["name"])}</a>' for c in day["hot"])
        parts.append(f"<p><b>{escape(CONFIG['hot']['name'])}：</b>{chips}</p>")
    if day["alerts"]:
        parts += [f"<h3>{escape(CONFIG['alerts']['name'])}</h3>", link_list(day["alerts"])]
    if day.get("tracking"):
        parts.append(f"<h3>{escape(CONFIG['tracking']['name'])}</h3><ul>")
        parts += [f'<li>【{escape(i["topic"])}】<a href="{escape(i["link"])}">{escape(i["title"])}</a> '
                  f'<small>— {escape(i["source"])}</small></li>' for i in day["tracking"]]
        parts.append("</ul>")
    if day["civic"]:
        parts += [f"<h3>{escape(CONFIG['civic']['name'])}</h3>", link_list(day["civic"])]
    for i, cat in enumerate(day["headlines"]):
        if not cat["articles"] and cat.get("each"):
            continue  # threshold-only sections disappear on quiet days
        # Use the current section name from config.toml, so a rename also applies to earlier days.
        name = CONFIG["category"][i]["name"] if i < len(CONFIG["category"]) else cat["name"]
        parts.append(f"<h3>{escape(name)}</h3>")
        if not cat["articles"]:
            parts.append("<p>無</p>")
        for a in cat["articles"]:
            parts.append(f'<p><a href="{escape(a["link"])}"><b>{escape(a["title"])}</b></a><br>'
                         f'<small>{escape(a["source"])}</small></p>')
            if a["summary"]:
                parts.append(f"<blockquote>{escape(a['summary'])}</blockquote>")
    marks = " · ".join(f'<a href="{escape(b["url"])}">{escape(b["name"])}</a>' for b in CONFIG.get("bookmark", []))
    if marks:
        parts.append(f"<hr><p><small>📊 數據：{marks}</small></p>")
    if day.get("failures"):
        parts.append(f"<p><small>⚠️ 今日抓取失敗：{escape('、'.join(day['failures']))}</small></p>")
    title = f"📰 {d:%a, %b} {d.day}"
    if day["alerts"]:
        title += " 🚨"
    return title, "\n".join(parts)


def write_feed(extra=None):
    """Write public/ from the saved days, plus `extra` (an unsaved preview of today) if given."""
    cfg = CONFIG["feed"]
    days = {p.stem: json.loads(p.read_text()) for p in DATA.glob("*.json")}
    if extra:
        days[extra["date"]] = extra
    items, sections = [], []
    for _, day in sorted(days.items(), reverse=True)[:CONFIG["keep_days"]]:
        title, body = render(day)
        sections.append(f'<section id="{day["date"]}"><h2>{escape(title)}</h2>\n{body}</section>')
        pub = format_datetime(datetime.fromisoformat(day["generated"]))
        items.append(f"""  <item>
    <title>{escape(title)}</title>
    <link>{escape(cfg['site_url'])}#{day['date']}</link>
    <guid isPermaLink="false">news-digest-{day['date']}</guid>
    <pubDate>{pub}</pubDate>
    <description>{escape(body)}</description>
  </item>""")
    PUBLIC.mkdir(exist_ok=True)
    (PUBLIC / "digest.xml").write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>{escape(cfg['title'])}</title>
  <link>{escape(cfg['site_url'])}</link>
  <description>不要錯過最重要的，平常的小事不一定要知道。原文不改寫。</description>
  <language>zh-TW</language>
{chr(10).join(items)}
</channel>
</rss>
""")
    # Item links point here (#date), so tapping a title in the reader opens the same content.
    (PUBLIC / "index.html").write_text(f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(cfg['title'])}</title>
<link rel="alternate" type="application/rss+xml" href="digest.xml">
<style>body{{max-width:40rem;margin:2rem auto;padding:0 1rem;font:16px/1.6 system-ui,sans-serif}}
section{{border-top:1px solid #ccc;padding-top:.5rem}}blockquote{{margin:.25rem 0 1rem;color:#555}}</style>
</head><body><p>RSS：<a href="digest.xml">digest.xml</a></p>
{chr(10).join(sections)}
</body></html>
""")


def main():
    if "--render" in sys.argv:
        write_feed()
    else:
        day = build()
        if "--preview" not in sys.argv:
            DATA.mkdir(exist_ok=True)
            (DATA / f"{day['date']}.json").write_text(json.dumps(day, ensure_ascii=False, indent=2))
        write_feed(extra=day)
    if "--open" in sys.argv:
        subprocess.run(["open", PUBLIC / "index.html"])


def build():
    now = datetime.now(TZ)
    today = now.date().isoformat()
    seen = seen_links(today)
    scores = {}
    day = {
        "date": today,
        "generated": now.isoformat(timespec="seconds"),
        "alerts": alerts(now, seen),
        "civic": civic(now, seen),
        "headlines": [{"name": cat["name"], "each": cat.get("each", False),
                       "articles": headlines(cat, now, seen, scores)} for cat in CONFIG["category"]],
        "scores": scores,  # top score per threshold source, shown or not — for tuning `min`
    }
    seen.update(a["link"] for cat in day["headlines"] for a in cat["articles"])
    day["hot"], tracked = hot(now, seen)
    shown = [a["title"] for cat in day["headlines"] for a in cat["articles"]] + [a["title"] for a in tracked]
    chips, watched, day["watch_hits"] = watch(now, seen, {c["name"] for c in day["hot"]}, shown)
    day["hot"] += chips
    day["tracking"] = tracked + watched
    day["failures"] = FAILURES
    for a in day["alerts"] + day["civic"]:
        print(f"{a['source']}: {a['title']}")
    print(f"🔥 {' · '.join(c['name'] for c in day['hot'])}")
    for a in day["tracking"]:
        print(f"📌 {a['topic']}: {a['title']}")
    for cat in day["headlines"]:
        print(f"{cat['name']}: {' / '.join(a['title'] for a in cat['articles']) or '無'}")
    print(f"scores: {scores}")
    print(f"watch hits: {day['watch_hits']}")
    if FAILURES:
        print(f"failures: {FAILURES}")
    return day


if __name__ == "__main__":
    main()
