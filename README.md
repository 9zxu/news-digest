# news-digest

```bash
uv run digest.py --render --open    # 改格式時用：不連網，用已存的資料重新排版，一秒完成
uv run digest.py --preview --open   # 看今天實際會產生什麼：重新抓新聞，但不存檔
```

每天早上 7 點產生**一篇** RSS 文章，用 iPhone 上的 NetNewsWire **只訂閱這一個 feed**。
全部用原文、不改寫，不用 AI。

**原則：不要錯過最重要的，平常的小事不一定要知道。**

## 每天那一篇長這樣

區塊標題用英文，只有台灣那區用中文。順序：World、台灣 → Trending、Alerts、Tracking、Civic → Developer → Data。

| 區塊 | 什麼時候出現 | 來源與判斷方式 |
|---|---|---|
| 🔥 Trending | 有進行中的大事時（一行關鍵字） | 颱風＋名字、寒流（中央氣象署）；維基百科首頁的「Ongoing」（例如俄烏戰爭）；中央社首頁的專題標籤（例如 2026亞運、九合一） |
| 🚨 Alerts | 有颱風、寒流、大地震時 | 中央氣象署的颱風警報、低溫特報（只放原文標題）；USGS 台灣周邊規模 6 以上的地震 |
| 📌 Tracking | 有進行中的事件時 | 每個主題每天 1 則，全自動，見下方「事件追蹤」 |
| 🗳️ Civic | 投票日前 30 天，或中選會有新公告時 | 中選會首頁行事曆倒數；中選會新聞稿與公告 RSS 中，跟公投、罷免、投票所、選舉公報、登記等有關的公告 |
| 🌍 World | 每天 | BBC World RSS 的第一篇（BBC 的 feed 照編輯判斷的重要性排序）；維基百科首頁「In the news」有新條目時再加 1 則（標準較全球化，排除體育） |
| 🇹🇼 台灣 | 每天 | 中央社首頁最大的那則頭條；抓不到時改用中央社政治 RSS |
| 💻 Developer | 超過門檻時，0–5 則 | Hacker News 的 AI 文章 ≥ 300 分、任何主題 ≥ 1000 分（大當機、重大資安漏洞）、alphaXiv 7 天內論文 ≥ 150 讚、Hugging Face 論文 ≥ 300 讚、GitHub Trending ≥ 1000 星／日 |
| 📊 Data | 每天（固定連結） | Epoch AI、Our World in Data、中選會選舉資料庫，自己看趨勢 |

已經出現過的文章不會重複出現。

## 事件追蹤（全自動）

兩岸政治、全球政治、公民參與（選舉、公投、罷免、學運、罷工、遊行、示威、抗議）、戰爭、半導體與科技地緣政治、重大災難與事故、疫情、民生大事、地震、颱風、奧運、世足、iOS 大版本發布這類**事件導向**的新聞：有事發生時每天跟進，平常不出現。不用手動設定。

- `config.toml` 的每條 `[[watch]]` 規則，都會用關鍵字（正規表示式）比對 `[tracking]` pool 裡過去 36 小時的新聞標題。來源包括 BBC、中央社、公視、MacRumors。
- **符合的文章數 ≥ `min_hits` 才算有大事**，主題會自動出現在「🔥 Trending」，並在「📌 Tracking」每天附 1 則新文章。報導變少後就自動消失。
- 例如 Apple 的規則只抓 `iOS 28` 這種大版本的正式發布，會排除 beta、28.1 小改版和傳聞。
- **中央社專題**（例如九合一）也會自動追蹤；同一件事如果已經有中央社專題或維基百科條目，就不會重複出現。
- 追蹤附上的文章會跳過「跟頭條是同一件事」的新聞（比對標題中共同的英文單字或中文雙字詞）。
- 每天各規則符合的篇數記在 `data/*.json` 的 `watch_hits`，可以用來調整 `min_hits`。

## 關鍵字規則在哪裡

所有規則都在 `config.toml`，判斷的程式在 `digest.py`：

| 規則 | 位置 |
|---|---|
| 事件追蹤：兩岸政治、全球政治、公民參與、戰爭…（關鍵字、門檻） | `config.toml` 的 `[[watch]]` |
| 事件追蹤掃描哪些新聞來源 | `config.toml` 的 `[tracking]` → `pool` |
| Developer 的門檻（HN、alphaXiv、HF、GitHub） | `config.toml` 的 `[[category]]` → `💻 Developer` |
| 判斷 HN 文章是否跟 AI 有關的關鍵字 | `digest.py` 的 `AI_WORDS` |
| 警報：颱風、寒流的關鍵字；地震規模門檻 | `config.toml` 的 `[alerts]` |
| 中選會公告：要包含／排除的關鍵字 | `config.toml` 的 `[civic]` |
| Trending 中要排除的中央社固定專欄 | `config.toml` 的 `[hot]` → `cna_exclude` |
| 每天各規則實際抓到幾篇、各來源的分數 | `data/YYYY-MM-DD.json` 的 `watch_hits`、`scores` |

## 使用方式

```bash
uv run digest.py                    # 正式執行：抓新聞、存 data/今天.json、產生 public/（GitHub Actions 每天跑這個）
uv run digest.py --preview --open   # 預覽今天：抓新聞、產生 public/ 並用瀏覽器打開，但不存 data/
uv run digest.py --render --open    # 只重新排版：用已存的 data/ 產生 public/，不連網，改格式時用
```

## 調整顯示格式

- **內容結構**（區塊順序、標題、emoji、顯示哪些欄位）：`digest.py` 的 `render()`。改完執行 `uv run digest.py --render --open`，馬上就能在瀏覽器看到結果。
- **每篇的標題**（例如 `📰 Mon, Oct 5`）：也在 `render()` 的最後幾行。
- **外觀**（字型、顏色、行距）：由 NetNewsWire 的主題決定，RSS 只傳送內容。`public/index.html` 的樣式只影響網頁版。
- `public/` 裡的檔案都是程式產生的，不要直接修改。

## 部署

`.github/workflows/digest.yml`：每天 06:30（台灣時間）用 GitHub Actions 執行，把 `data/` 存回 repo，再把 `public/` 發布到 GitHub Pages。
訂閱網址：`https://<帳號>.github.io/<repo>/digest.xml`。

## 檔案

| 檔案 | 用途 |
|---|---|
| `config.toml` | 所有來源、門檻、追蹤主題、書籤 |
| `digest.py` | 抓資料、挑選、寫出 feed |
| `data/YYYY-MM-DD.json` | 每天選出的內容與分數（也用來避免重複；之後給 MCP 用） |
| `public/digest.xml` | 給 NetNewsWire 訂閱的 feed，保留最近 14 天 |
| `sources.md` | 候選來源與測試紀錄，包含其他推薦的免費來源 |

## 進度

- [x] 每天一篇：世界、台灣頭條；AI 只在超過門檻時出現
- [x] 警報（颱風、寒流、地震）、公民參與（中選會）
- [x] 事件追蹤（關鍵字規則自動偵測、中央社專題）
- [x] 近期大事關鍵字列
- [ ] 部署到 GitHub Actions 和 GitHub Pages
- [ ] 調整門檻（觀察一兩週的 `scores`）
- [ ] MCP server：讓 Claude 讀當天選出的文章內文，用初學者的角度解釋背景、關鍵人物和不同觀點（只用來學習，不用來整理新聞）

## 注意

- **抓取失敗會顯示在 feed 裡**：任何來源失敗時，那篇最下方會出現「⚠️ Failed to fetch today: …」，避免把「抓不到」誤以為「沒大事」。
- **抓網頁的來源**：中央社首頁、中選會首頁、GitHub Trending 都是解析網頁；alphaXiv 用的是網站內部的 API（沒有公開文件），網站改版時可能失效。失效時程式會印出 `!` 開頭的警告，但不會中斷。
- **中央氣象署的使用聲明**：只能呈現標題、要連回原文，而且不得改寫或製作衍生產品。所以警報只放原文標題，也不會交給 MCP 和 AI。
- **地震用 USGS**：中央氣象署的 RSS 沒有地震資料。若想改用台灣的震度判斷，可以申請中央氣象署的開放資料 API key（顯著有感地震報告 E-A0015-001）。
- **Hugging Face 週末沒有論文**，所以兩天前剛好是週末時，這一項不會出現。
- **Python 3.13 的 SSL**：公視和中央氣象署的憑證會被 Python 3.13 的嚴格檢查擋下。程式仍然會驗證憑證，只是關掉 `VERIFY_X509_STRICT` 這條規則。
- **GitHub 排程**：常會延遲，而且是從國外的機器執行；如果中央氣象署或中選會擋國外 IP，警報或公民參與會缺資料，第一次部署後要確認。
