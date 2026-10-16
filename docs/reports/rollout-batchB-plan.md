# 全国展開 第2回(関東・甲信越)の計画と事前基準(結果を見る前に記録)

関連: D-088 / 前提: `docs/reports/rollout-batchA-result.md`

## 対象
コードは v11 のまま(ロジックは変えない)。区(政令市の区)を除く、軽量形式。東京都は特別区23を含む(`record_scope=municipality`)。
| 県 | route | 件数 |
|---|---|---|
| 茨城県 | `actions_direct_v11_ibaraki` | 44 |
| 栃木県 | `actions_direct_v11_tochigi` | 25 |
| 群馬県 | `actions_direct_v11_gunma` | 35 |
| 埼玉県 | `actions_direct_v11_saitama` | 63 |
| 千葉県 | `actions_direct_v11_chiba` | 54 |
| 東京都 | `actions_direct_v11_tokyo` | 62 |
| 神奈川県 | `actions_direct_v11_kanagawa` | 33 |
| 新潟県 | `actions_direct_v11_niigata` | 30 |
| 山梨県 | `actions_direct_v11_yamanashi` | 27 |
| 長野県 | `actions_direct_v11_nagano` | 77 |
| 計 | | 450(`config/auto_crawl.json`) |

## 事前基準(第1回と同じ。正解データは作らない)
| # | 項目 | 基準 | 満たさないとき |
|---|---|---|---|
| 1 | 取得失敗率(`fetch_failed`+`robots_blocked`、`no_url`は除く) | 県ごとに10%以下 | 失敗の理由別に分析。403/429/タイムアウトの集中はWAF/IPブロックの疑い → プロキシ経路を提案。次の回に進まない |
| 2 | ブロック兆候(robots.txt・サイトマップを除くリクエストの403・429、CAPTCHA相当) | 403が出た自治体が全体の5%未満 | 同上 |
| 3 | 平均リクエスト数 / 平均容量 | 15以下 / 35KB以下 | 探索予算・形式の見直し |
| 4 | 確定ページの妥当性(題名・施設の例で判断) | 既知の誤りの型(予約・使用料(金)・使用許可・整備事業・開放事業・専門学校・単一施設・お知らせ)に当たるものが確定数の10%以下 | 誤確定のパターンを分析。次の回に進まない |

報告のみ: 確定率、`hub_multiple`/`hub_not_found` の割合、CMSの分布、`needs_headless` の件数、robots.txtが403の自治体数、東京都の特別区の結果(区ごとにホストが違う)。

## 次の回
基準1〜4を満たせば、第3回(東海・近畿の残り、222件)に進む案を出す(ユーザーの指示を待つ)。
