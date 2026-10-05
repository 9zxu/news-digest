# news-digest

Feed: https://9zxu.github.io/news-digest/digest.xml

```bash
uv run digest.py --render --open    # 改格式時用：不連網，用已存的資料重新排版，一秒完成
uv run digest.py --preview --open   # 看今天實際會產生什麼：重新抓新聞，但不存檔
```

## Entry points

- `config.toml` — 所有來源、關鍵字、門檻
- `digest.py` → `main()` → `build()` 抓資料，`render()` 排版
- `data/YYYY-MM-DD.json` — 每天的結果，含 `scores`、`watch_hits`
- `.github/workflows/digest.yml` — 每天 06:30（台灣時間）執行
- `sources.md` — 來源測試紀錄

本機 push 前先 `git pull`（Actions 每天會 commit `data/`）。
