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
1. robots.txt取得・解釈 → 2. トップページ取得(リダイレクト先・ステータス・所要時間) → 3. JS描画要否判定(本文もリンクも少なく画像も少ない場合のみ) → 4. 同一サイトのリンク抽出(文言・URL・領域。画像のみのリンクはファイル名を仮ラベルに) + メニュー区分の検出 → 5. サイトマップ(robots記載 → CSVの候補 → /sitemap.xml の順に最大3件試行、indexは子5件まで)→ 件数・lastmod分布・トップレベルパス別件数 → 6. CMS推定(generator/HTML/URL形式のシグネチャ) → 7. ハブ探索 → 8. 判定。

### ハブ探索(`pipeline._find_hub` / `hub.py`)
- **候補の採点**: リンク文言(NFKC正規化)をスポーツ語(スポーツ施設・体育施設・運動施設など)、探索語(施設を探す・町の施設など)、大分類(教育・文化・くらしなど)、サイトマップページで採点。お知らせ記事らしい文言は取得も採用もしない。
- **1段目**: スコア2以上の候補を上位6件まで取得し、施設名リンク(体育館・グラウンド・プール等)の数とtitle/h1で再採点。ページ内のリンクを2段目の候補にする。
- **2段目**: 2段目の候補のうち有望なもの(スコア5以上)を上位3件まで取得して再採点。
- **深さ3の記録**: 2段目のページ内のリンクも候補として記録する(取得はしない)。
- **ラベルの種類**: 専用(スポーツ・体育など)/ 複合(観光・文化・スポーツなど)/ 汎用(公共施設一覧など)/ 大分類(教育・くらしなど)。
- **3段目の確認**: 深さ3の候補のうち、専用ラベルでスコア8以上のものを最大2件取得して施設名リンクを確認する。
- **強いラベル優先**: スポーツ施設/体育施設/運動施設を含むラベルを、「スポーツ」だけ等の弱いラベルより先に評価する。
- **採用(精度優先)**: ページを取得して施設名リンクを確認できた候補だけ。専用ラベルは施設名リンク2件以上(1件だけのページは一段上のカテゴリであることが多い)。複合ラベルは強い語(スポーツ施設等)を含み3件以上。汎用ラベルは3件以上(専用ページが無いときのみ、`quality=generic`)。大分類・サイトマップ・お知らせ記事は採用しない。専用ラベルのうち浅い(トップに近い)ものを選び、同じ深さの次点との差が4未満なら `hub_multiple`。ページ未確認で有望な候補だけがあるときも `hub_multiple`。
- リクエスト上限は1自治体30件。robotsで禁止されたパスは候補から除外する。
- 一時的な失敗(408/429/5xx/タイムアウト/接続リセット)は1回だけ再試行。

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

## ジャンルと施設一覧の階層について(2026-10-15 ユーザー指摘)
自治体ごとに、スポーツ施設を「スポーツ施設一覧」として専用にまとめているところと、「公共施設一覧」にまとめているところがある。両者は固定の親子関係ではない。そのため、スポーツ専用の一覧があればそれを(`quality=specific`)、無ければ汎用の施設一覧を(`quality=generic`)入口とし、他ジャンルの入口も別々に探す。


## 自動クロール(マージをきっかけにした実行、D-056)
`main` に `src/**` か `config/auto_crawl.json` の変更がマージされると、`auto-crawl` ワークフローが `config/auto_crawl.json` の `targets`(県と route)を `crawl` ワークフローで実行し、結果を `main` にコミットする。
- コードを変えたら、`config/auto_crawl.json` の route を新しい名前に更新する(結果がある route は実行されない)
- 止める: `enabled: false`、またはコミットメッセージに `[skip crawl]`
- 手動実行: Actions の `auto-crawl`(設定どおり)または `crawl`(県・routeを指定)

## 全国実行用の軽量形式(D-062)・範囲指定(D-063)
- `localgov-crawler run --compact`: インデントなしの1行JSONで保存する(`run.compact=true`)。`nav_links`(トップページ内のaタグのリンク文言・URL・領域。同一サイト内、最大400件、画像のみのリンクはalt/ファイル名)は**残す**(D-065)。
- `list/run --scope municipality|designated_city_ward`: 政令市の区(171件)を除く/区のみ。
- `config/auto_crawl.json` の各 target は `scope`(省略可)と `compact`(省略可、既定false)を持てる。`crawl` ワークフローにも同名の入力がある。
