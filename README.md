# local-gov-clawler

全国の地方自治体Webサイトの**浅い構造解析**クローラー。トップページ・robots.txt・サイトマップ・ナビゲーションを解析し、ジャンル別の入口ページ(最初は「スポーツ施設」)の候補を見つける。結果はこのリポジトリに保存する。

- 設計資料: [docs/handoff.md](docs/handoff.md) / 確定仕様: [docs/spec.md](docs/spec.md)
- 決定ログ: [docs/decisions.md](docs/decisions.md) / 進捗: [docs/progress.md](docs/progress.md) / 指示ログ: [docs/instructions.md](docs/instructions.md)
- 自治体マスタ: [data/input/municipalities_master.csv](data/input/municipalities_master.csv)(1,918行)
- 結果: `data/results/<route>/<都道府県コード>/<自治体コード>.json`、集計: `data/summary/`

## 使い方
```
pip install -e ".[dev]"
pytest -q
localgov-crawler list --prefecture 奈良県
localgov-crawler run --prefecture 奈良県 --route local
localgov-crawler summarize --route local
```
GitHub Actionsでは `crawl` ワークフローを手動実行する(パイロット: prefecture=奈良県, route=actions_direct)。コマンドの詳細は [docs/spec.md](docs/spec.md)。

## 取得ルール
robots.txt遵守 / 1ホスト1リクエスト/秒以下 / UAに連絡先 / CAPTCHA・WAFは突破しない / 予約システムには入らない。
問題があれば、UAに記載のとおりこのリポジトリのIssueへ連絡してほしい。

## 状態
パイロット(奈良県)の実装が完了し、実クロール待ち。現況は [docs/progress.md](docs/progress.md)。
