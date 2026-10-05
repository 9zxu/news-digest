"""MCP server: lets Claude read the digest and the articles behind it, so it can teach the background.
It doesn't pick or summarize news — digest.py does the picking, without AI.

Run: uv run --group mcp mcp_server.py
"""

import json
from datetime import datetime
from pathlib import Path

import trafilatura
from mcp.server.mcpserver import MCPServer

from digest import TZ, get

ROOT = Path(__file__).parent
RAW = "https://raw.githubusercontent.com/9zxu/news-digest/main/data/{}.json"  # what Actions committed, no pull needed

mcp = MCPServer("news-digest")


def load_day(date):
    try:
        return json.loads(get(RAW.format(date)))
    except Exception:
        path = ROOT / "data" / f"{date}.json"
        if path.exists():
            return json.loads(path.read_text())
        raise ValueError(f"No digest for {date}")


def entries(day):
    """Every linked item in the day's post, numbered. 中央氣象署 items are left out: its terms forbid derived use."""
    out = [{"section": cat["name"], **a} for cat in day["headlines"] for a in cat["articles"]]
    out += [{"section": f"Tracking · {a['topic']}", **a} for a in day.get("tracking", [])]
    out += [{"section": "Civic", **a} for a in day.get("civic", [])]
    out += [{"section": "Alerts", **a} for a in day.get("alerts", []) if a["source"] != "中央氣象署"]
    keep = ("section", "title", "source", "summary", "link")
    return [{"id": i, **{k: e[k] for k in keep if e.get(k)}} for i, e in enumerate(out, 1)]


@mcp.tool()
def get_digest(date: str = "") -> dict:
    """The items in one day's digest (default: today, Taiwan time), numbered, plus the trending keywords.
    date: YYYY-MM-DD"""
    date = date or datetime.now(TZ).date().isoformat()
    day = load_day(date)
    return {"date": date, "trending": [c["name"] for c in day.get("hot", [])], "items": entries(day)}


@mcp.tool()
def read_article(url: str) -> str:
    """Main text of an article page (ads, menus and comments stripped), up to ~12,000 characters."""
    if "cwa.gov.tw" in url:
        return "中央氣象署的使用聲明不允許解析其內容製作衍生產品，請直接開啟連結閱讀。"
    text = trafilatura.extract(get(url).decode("utf-8", "replace"), include_comments=False) or ""
    return text[:12000] or "Couldn't extract the article text; the page may need JavaScript. Open the link instead."


@mcp.prompt()
def explain(item: str = "", date: str = "") -> str:
    """Teach me one item from the digest as a beginner: background, who's involved, why it matters, viewpoints."""
    which = f"第 {item} 則" if item else "我接下來指定的那則（先列出今天的項目讓我選）"
    return f"""我是看新聞的初學者。用 news-digest 的工具：
1. 呼叫 get_digest（date={date or "今天"}），找到{which}。
2. 用 read_article 讀原文。如果需要背景，可以再讀文中提到的其他連結。
3. 教我看懂這則新聞，不要只是摘要原文：
   - 背景：事情怎麼走到今天，3–5 個時間點
   - 關鍵角色：人物、國家、組織，各自想要什麼
   - 為什麼重要：對世界、對台灣、對我（資工系學生）
   - 不同立場：至少兩種觀點；分清楚哪些是事實、哪些是評論
   - 名詞解釋：初學者可能不懂的詞
   - 最後問我一個問題，讓我自己想
引用原文要標出處；不確定的地方直接說不確定。"""


if __name__ == "__main__":
    mcp.run()
