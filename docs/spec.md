# 仕様(確定分)

出典: `docs/handoff.md`(設計資料)+ `docs/decisions.md`。矛盾する場合は decisions.md が新しい。

## 目的とスコープ
- 全自治体Webサイトの**浅い構造解析**。トップ、robots.txt、サイトマップ、トップから2階層程度まで。
- ジャンル別の入口(ハブ)ページ候補への到達まで。最初のジャンルは `sports_facility`(スポーツ施設・公共グラウンド)で、構造解析の受け入れテストの物差し。
- 施設情報の抽出(グラウンドゴルフ可否など)は後続フェーズ。

## 非目標
全ページクロール / 予約システム / CAPTCHA・WAF突破 / robots禁止パスの取得 / 複数IP分散によるレート制限回避 / DOM構造の保存 / ページ本文の転載。

## 取得ルール
robots.txt遵守、1ホスト1req/秒以下、UAに連絡先、自治体単位の並列、WAFで弾かれたら`fetch_failed`(理由つき)で終了、規約でクロール禁止のサイトは対象外。

## 入力
`data/input/municipalities_master.csv`(1,918行 = 市区町村1,747 + 政令市の区171)。主な列: 地方公共団体コード、名称、`official_website_url`、`xml_sitemap_url` / `xml_sitemap_candidate_url`。

## 1自治体の処理(`pipeline.analyze`)
1. robots.txt取得・解釈 → 2. トップページ取得(リダイレクト先・ステータス・所要時間) → 3. JS描画要否判定 → 4. 同一サイトのリンク抽出(文言・URL・領域) + メニュー区分の検出 → 5. サイトマップ(robots記載 → CSVの候補 → /sitemap.xml の順に最大3件試行、indexは子8件まで)→ 件数・lastmod分布・トップレベルパス別件数 → 6. CMS推定(generator/HTML/URL形式のシグネチャ) → 7. ハブ候補スコアリング → 上位4候補ページを取得して施設名リンク数で再採点、その先のリンクも候補化 → 8. 判定。

## 出力(`data/results/<route>/<pref>/<code>.json`、schema_version=1)
`municipality` / `run` / `outcome` / `failure_class` / `needs_review` / `ai_needed` / `site_profile`(robots, top, rendering, sitemap, cms, fetch_method, used_proxy) / `nav_links` / `menu_labels` / `genre_entrypoints`(decision, selected, candidates, blocked_by_robots) / `requests`。
判定の出所は `provenance`(auto / ai / manual)。現状はauto のみ。

### outcome
| outcome | 意味 | 次の扱い |
|---|---|---|
| hub_selected | ハブ候補が1つに絞れた(スコア≥8 かつ次点との差≥4、または唯一) | 完了(auto) |
| hub_multiple | 候補が複数で絞れない | AI判定へ(`ai_needed`) |
| hub_not_found | 候補なし | AI判定へ(`ai_needed`) |
| needs_headless | 本文が空に近くJS描画が必要そう | ヘッドレス取得へ(未実装) |
| fetch_failed | 取得できなかった | `failure_class` で原因別に手動確認/プロキシ検討 |
| robots_blocked | トップページがrobotsで禁止 | 対象外 |
| no_url | マスタに公式URLがない(5件) | 手動で補完 |

### failure_class
`timeout` / `dns` / `tls` / `conn_refused` / `conn_reset` / `connect_error` / `proxy_error` / `too_many_redirects` / `http_403` / `http_404` / `http_429` / `http_4xx` / `http_5xx` / `robots_unreachable` / `other`

## データモデル(handoff §5との対応)
- municipalities / site_profiles / genre_entrypoints / nav_links → JSONの各セクション。`merge-db` でSQLiteを生成(派生物)。
- pages(生データ層)・extractions(構造化層)は後続フェーズ。未作成。

## 受け入れテスト(暫定)
奈良県で、目視の正解データ10件に対し、ハブ候補上位5件への到達率 **8割**(handoff §9。ユーザーと調整可)。測り方は `data/ground_truth/README.md`。

## 計測する指標
outcome別件数 / プログラムのみで確定できた割合 / AIに回る件数 / 1自治体あたりリクエスト数・所要時間 / ヘッドレス要の割合 / route間の失敗率(`localgov-crawler compare`)。

## コマンド
```
localgov-crawler list      --prefecture 奈良県
localgov-crawler run       --prefecture 奈良県 --route local            # 結果は data/results/local/29/*.json
localgov-crawler run       ... --route proxy --use-proxy                # CRAWL_PROXY_URL 必須
localgov-crawler summarize --route local                                # data/summary/local.{json,md}
localgov-crawler evaluate  --route local --truth data/ground_truth/sports_hub_nara.csv
localgov-crawler compare   actions_direct proxy local
localgov-crawler merge-db  --route local --db out/crawl.sqlite
```
GitHub Actions: `crawl` ワークフローを手動実行(`.github/workflows/crawl.yml`)。
