# ユーザー指示ログ

ユーザーからの指示を日付つきで追記していく(古いものを消さない)。

## 2026-10-14

### 初回依頼
> 全国の地方自治体のWebサイトから情報を集めるクローラーを作りたい。集めた情報はリポジトリに保存する。
> またプロジェクトで指定したことや進捗なども常にリポジトリに保存する。
> 作成するシステムの概要は添付の資料参照して。また、地方自治体のリストも添付するね

添付:
- 引き継ぎ資料 → `docs/handoff.md`
- 自治体マスタ(1,918行、XMLサイトマップ調査 Batch 8) → `data/input/municipalities_master.csv`
- XMLサイトマップ調査レポート → `docs/reports/xml_sitemap_research_batch8_20261014.md`

### 質問への回答(未決事項の確定)
- 実装言語: **Python**
- パイロット県: **奈良県**(39自治体)
- リポジトリ: **公開**

### 2026-10-14 (続き)
- 「crawlが見つけられない」→ 手動実行ワークフローは `main` に無いとActions一覧に出ないことを説明。
- 「PRを作ってmainにマージして」→ `claude/local-government-crawler-9nb679` から `main` へPRを作成してマージする。
- 「crawlを実行した結果を見て」(ユーザーがActionsで奈良県を実行した後)→ 結果を取得・分析し、`docs/reports/pilot-nara-run1.md` に記録。結果JSONを `data/results/actions_direct/29/` に保存。
- 「1を進めて」(改善案1=ロジック改善6項目の実装)→ 実装してテスト追加、決定ログD-017〜D-024に記録。
- 「正解データ10件…どこの自治体を見ればいいの?」→ 奈良県の10自治体を選定し、`data/ground_truth/sports_hub_nara.csv` に事前記入、選定理由と記入手順を `data/ground_truth/README.md` に記載。
- 「記入終わったよ」→ ユーザーが `data/ground_truth/sports_hub_nara.csv` に正解URLを記入(ブランチにコミット済み)。第1回(改善前)を採点し、`docs/reports/pilot-nara-baseline-vs-ground-truth.md` に記録。メモ列: 葛城市・斑鳩町は「純粋なスポーツ施設の一覧ではない」、黒滝村は「公共施設一覧の中に混じっている」。
- 「PRを作ってmainにマージして」(2回目)→ 改善版(D-017〜D-027、正解データ、採点)をPR化して `main` にマージ。マージ後に奈良県を再実行して改善の効果を測る。
