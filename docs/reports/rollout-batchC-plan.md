# 全国展開 第3回(残り25府県を一括)の計画と事前基準(結果を見る前に記録)

関連: D-090 / 前提: `docs/reports/rollout-batchB-result.md`

## 経緯
ユーザー指示(2026-10-16「第３回やってほしいんだけど、もっとまとめてやっていいよ」)により、第3回〜第5回(東海・近畿の残り、中国・四国、九州・沖縄)と、これまで割り当てが漏れていた富山県・石川県を、1回にまとめて実行する。第1回・第2回で事前基準をすべて満たした(取得面の問題なし)ため。
(訂正: 以前の計画「残り42都道府県・1,575件」の内訳には富山県・石川県が入っておらず、5回の合計が漏れていた。区を除く1,747件のうち、残りは25府県・713件。)

## 対象
コードは v11 のまま。区(政令市の区)を除く、軽量形式。25府県を並列で実行。
| 県 | route | 件数 |
|---|---|---|
| 富山県 | `actions_direct_v11_toyama` | 15 |
| 石川県 | `actions_direct_v11_ishikawa` | 19 |
| 岐阜県 | `actions_direct_v11_gifu` | 42 |
| 静岡県 | `actions_direct_v11_shizuoka` | 35 |
| 三重県 | `actions_direct_v11_mie` | 29 |
| 滋賀県 | `actions_direct_v11_shiga` | 19 |
| 京都府 | `actions_direct_v11_kyoto` | 26 |
| 兵庫県 | `actions_direct_v11_hyogo` | 41 |
| 和歌山県 | `actions_direct_v11_wakayama` | 30 |
| 鳥取県 | `actions_direct_v11_tottori` | 19 |
| 岡山県 | `actions_direct_v11_okayama` | 27 |
| 広島県 | `actions_direct_v11_hiroshima` | 23 |
| 山口県 | `actions_direct_v11_yamaguchi` | 19 |
| 徳島県 | `actions_direct_v11_tokushima` | 24 |
| 香川県 | `actions_direct_v11_kagawa` | 17 |
| 愛媛県 | `actions_direct_v11_ehime` | 20 |
| 高知県 | `actions_direct_v11_kochi` | 34 |
| 福岡県 | `actions_direct_v11_fukuoka` | 60 |
| 佐賀県 | `actions_direct_v11_saga` | 20 |
| 長崎県 | `actions_direct_v11_nagasaki` | 21 |
| 熊本県 | `actions_direct_v11_kumamoto` | 45 |
| 大分県 | `actions_direct_v11_oita` | 18 |
| 宮崎県 | `actions_direct_v11_miyazaki` | 26 |
| 鹿児島県 | `actions_direct_v11_kagoshima` | 43 |
| 沖縄県 | `actions_direct_v11_okinawa` | 41 |
| 計 | | 713(`config/auto_crawl.json`) |

## 運用面の変更
- 25府県が同時に結果を `main` にコミットするため、`crawl.yml` のpush再試行を5回→10回に増やし、待ち時間にばらつき(0〜4秒)を加えた(コミットの競合対策)。コミットに失敗した府県は、結果の無いrouteなので、次の `auto-crawl` で再実行される。

## 事前基準(第1回・第2回と同じ。正解データは作らない)
| # | 項目 | 基準 | 満たさないとき |
|---|---|---|---|
| 1 | 取得失敗率(`fetch_failed`+`robots_blocked`、`no_url`は除く) | 府県ごとに10%以下 | 失敗の理由別に分析。403/429/タイムアウトの集中はWAF/IPブロックの疑い → プロキシ経路を提案 |
| 2 | ブロック兆候(robots.txt・サイトマップを除くリクエストの403・429) | 403が出た自治体が全体の5%未満 | 同上 |
| 3 | 平均リクエスト数 / 平均容量 | 15以下 / 35KB以下 | 探索予算・形式の見直し |
| 4 | 確定ページの妥当性(題名・施設の例で判断) | 既知の誤りの型(予約・使用料(金)・使用許可・整備事業・開放事業・専門学校・単一施設・お知らせ・利用案内)に当たるものが確定数の10%以下 | 誤確定のパターンを分析 |

報告のみ: 確定率、`hub_multiple`/`hub_not_found` の割合、CMSの分布、`needs_headless` の件数、robots.txtが403の自治体数、コミットに失敗した府県の有無。

## 次
全国(区を除く1,747件)が一巡する。次の段階の案: (a) 全国の結果をもとにしたルール見直し(全体の差分、手動確認の候補つきリスト)、(b) 政令市の区171件の扱い(D-063)、(c) `needs_headless` と取得失敗の再取得、(d) 抽出フェーズ(ハブからの施設情報)。ユーザーの指示を待つ。
