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

## 「一覧ページ」の人間の判断基準(2026-10-16 ユーザー、D-075)
人間は次の2点で一覧と判断する: ①リスト形式になっている(人間が見て)、②体育館・グラウンド・広場など、運動を連想する施設がいくつか並んでいる。
現行の近似: 施設名の語を含むaタグリンクの数(`facility_link_count`)。リンクでない本文の施設語は診断(`body_terms`)のみで、判定には使っていない。

## 施設の数え方(v10、D-079)
`hub.page_features` が、候補ページの「施設の数」(`facility_link_count`)を返す。リンクと、リスト/表の項目(li・dt・dd・td・th)の文字から、施設語(`FACILITY_NAME`)を含むものを集め、施設名(先頭の【…】を除き、最後の施設語まで)で重複をまとめる。強いお知らせ語(`STRONG_NEWS`)を含むものは数えない。弱い語(`SOFT_NOISE`)を含むものは、きれいな施設名が2件以上あるか、合計3件以上のときに数える。
## 規則R(v10、D-080)
`hub.ascend`: 確定した(または1位の)ページが `sports_other` で、1つ上の階層(`parent_check`)の題名が専用ラベルかつ施設2件以上なら、親ページを採る。

## v11の数え方と順序(D-083)
`page_features(rich)`: 専用ラベル(sports_pure)と強い語を含む複合ラベルのページだけ rich(本文の項目・弱いお知らせ語・同じ施設は1件)。それ以外は v9 のリンクだけの数え方。`decide`: 専用ラベル → 強いラベル → 浅い → スコアの順。

## v12.1 同点のタイブレーク(D-103/D-104)
`hub.decide` で同点(同じ深さで、スコア差が MARGIN 未満)になったとき、`hub.break_tie` が順に絞る。1件に絞れなければ hub_multiple のまま。同点でない自治体の判定は変えない。
- T4: 『…について』を含むラベルは、含まない候補があれば除く
- T1: 名前に『一覧』がある sports_pure/sports_other だけを残す(複合ラベルの『…連絡先一覧』は対象外)
- T2: sports_pure の候補が、他のすべての候補の親(URLのディレクトリ)なら、その親を採る
- T3(`hub.ascend`): hub_multiple で、同点の上位2件がどちらも1つの施設の名前(『・』を含まない)のとき、1つ上のページが汎用ラベル(公共施設利用案内 など)で施設リンク3件以上なら、それを採る(quality=generic)。予約・申込のタイトルは除く
- 同じページ(http/https・www・末尾スラッシュ・index.html だけが違う)は、候補を1件にまとめる
- `localgov-crawler redecide`: 保存済みの結果から判定だけをやり直す(サイトには接続しない)
