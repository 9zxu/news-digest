# 候選來源

目前採用的頭條來源見 README.md。下面是測試過的所有候選來源。

## 頭條訊號（2026-10-05 測試）

| 來源 | 結果 |
|---|---|
| BBC World RSS | ✅ 照編輯判斷的重要性排序，不是照時間 → 第一篇就是頭條 |
| 中央社首頁 | ✅ `<a class="majorNewsClick">` 裡的 `<h2 class="biggest">` 就是頭條 |
| HN Algolia API `hn.algolia.com/api/v1/search_by_date` | ✅ 有分數，可以篩時間 |
| hnrss.org | ⚠️ 測試時回傳 502，不穩定，改用 Algolia API |
| 公視 RSS | ❌ 大致照時間排序，看不出頭條 |
| 中央社 RSS（各分類） | ❌ 照時間排序 |
| Techmeme RSS | ⚠️ 網站本身由編輯排序，但 feed 是照時間排序，而且不只 AI |
| Google 新聞 台灣 RSS | ⚠️ 演算法排序，混入很多聳動標題的媒體 |
| Wikimedia featured API（`api.wikimedia.org/feed/v1/wikipedia/en/featured/YYYY/MM/DD` 的 `news`） | ✅ 維基百科首頁「新聞動態」，門檻高、中立，適合初學者；但一天只更新幾則，且包含體育 |

2026-10-05 用 curl 實際測試過，「項目數」是當時 feed 裡的文章數量（不是每天的發文量）。

## 事件與門檻來源（2026-10-05 測試）

| 來源 | 網址 | 結果 |
|---|---|---|
| Hugging Face Daily Papers | `https://huggingface.co/api/daily_papers?date=YYYY-MM-DD` | ✅ 有 upvotes；週末是空的。10/1 最高 521、10/2 最高 219 |
| GitHub Trending | `https://github.com/trending?since=daily`（網頁） | ✅ 可解析「stars today」，第一名 1,430 |
| USGS 地震 | `https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&...` | ✅ 免 key，可用經緯度範圍與規模篩選 |
| 中央氣象署地震 | RSS 沒有 | ❌ 要用開放資料平臺的 API key |
| 中選會首頁 | `https://www.cec.gov.tw/` 內的 `__NUXT_DATA__` | ✅ 有行事曆（投票日）和新聞稿、公告、最新消息；但文章網址是 JavaScript 產生的 |
| 中央社 體育 | https://feeds.feedburner.com/rsscna/sport | ✅ |
| BBC Sport | https://feeds.bbci.co.uk/sport/rss.xml | ✅ |

## 🌍 世界

| 來源 | Feed URL | 狀態 | 項目數 | 備註 |
|---|---|---|---|---|
| BBC World | https://feeds.bbci.co.uk/news/world/rss.xml | ✅ 200 | 25 | 英文，標題短 |
| The Guardian World | https://www.theguardian.com/world/rss | ✅ 200 | 45 | 英文，量多，需要限量 |
| 中央社 國際 | https://feeds.feedburner.com/rsscna/intworld | ✅ 200 | 20 | 中文 |

## 🤖 AI

| 來源 | Feed URL | 狀態 | 項目數 | 備註 |
|---|---|---|---|---|
| Simon Willison | https://simonwillison.net/atom/everything/ | ✅ 200 | 30 | 技術向，更新頻繁，含很多短連結 |
| Import AI（Jack Clark） | https://importai.substack.com/feed | ✅ 200 | 20 | 週報，研究向 |
| The Batch（Andrew Ng） | 未找到 | ❓ | — | 可能沒有公開 RSS，待查 |

## 🇹🇼 台灣

| 來源 | Feed URL | 狀態 | 項目數 | 備註 |
|---|---|---|---|---|
| 公視新聞網 | https://news.pts.org.tw/xml/newsfeed.xml | ✅ 200 | 25 | 公共電視，無廣告 |
| 中央社 政治 | https://feeds.feedburner.com/rsscna/politics | ✅ 200 | 20 | 中文 |
| 報導者 | https://www.twreporter.org/a/rss2.xml | ✅ 200 | 10 | 深度報導，發文量少 |
| Focus Taiwan（中央社英文） | https://focustaiwan.tw/rss | ❌ 404 | — | 需要找正確的網址 |

## 🌦️ 天氣（中央氣象署）

| 來源 | Feed URL | 狀態 | 備註 |
|---|---|---|---|
| 警報、特報 | https://www.cwa.gov.tw/rss/Data/cwa_warning.xml | ✅ 200 | 颱風、豪雨、強風等，平常是空的或很少 |
| 縣市 36 小時預報 | `https://www.cwa.gov.tw/rss/forecast/36_XX.xml` | ✅ 200 | 一個縣市一個 feed，標題就是預報內容 |

縣市代碼：01 臺北市、02 高雄市、03 基隆市、04 新北市、05 桃園市、06 新竹縣、07 苗栗縣、08 臺中市、
09 彰化縣、10 南投縣、11 雲林縣、12 嘉義縣、13 臺南市、14 新竹市、15 屏東縣、16 嘉義市、17 宜蘭縣、
18 花蓮縣、19 臺東縣、20 澎湖縣、21 金門縣、22 連江縣

預報 item 的標題範例：`臺北市10/05 今晚明晨 陰短暫陣雨 溫度: 24 ~ 25 降雨機率: 30% (10/05 17:00發布)`

⚠️ **使用聲明**（feed 內的 copyright 欄位）：允許個人以 RSS reader 使用，並可在私人、非商業用途中
呈現**標題**，但必須連回原文、標明「中央氣象署」，而且**不得更改內容或解析後製作衍生產品**。
→ 做法：天氣只**原封不動放標題**，附上連結和來源，不要用 AI 改寫或摘要。
→ 若之後想做更多加工（例如只在降雨機率 > 50% 時提醒），改用「氣象資料開放平臺」
  （opendata.cwa.gov.tw，需要免費註冊 API key），它採用政府資料開放授權，可以製作衍生內容（待確認條款）。

## 待辦

- [ ] 從上面每類挑 1–3 個來源
- [ ] 找 The Batch 和 Focus Taiwan 的正確 feed
- [ ] 天氣要放哪個縣市？
- [ ] 實際記錄幾天，看每個來源一天發幾篇
