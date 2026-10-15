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
- 「crawlを実行した結果を見て」(2回目、改善版)→ run #2 の結果を取得して採点・分析し、`docs/reports/pilot-nara-run2.md` に記録。

## 2026-10-15
- 香芝市: クローラーが確定した `life/7/41/179/` の方が良い(複数URLを正解に持てるようにする)。
- 葛城市・斑鳩町・橿原市・河合町の小分類ページ(純粋な一覧ではない)は、ハブとして許容する。
- 見直しの実装(精度優先・専用性で選ぶ・深さ3を候補化・個別施設を除外)を進める。検証用の正解データは `data/ground_truth/sports_hub_nara_heldout.csv` に置く(質問「正解データはどこに置けば良い?」への回答)。
- 「正解データ更新したよ」→ 検証用 `sports_hub_nara_heldout.csv` を記入(9件+「なし」1件)。見直し前の結果を集計値のみで採点し `docs/reports/pilot-nara-heldout-baseline.md` に記録。
- 「PRを作ってmainにマージして」(3回目)→ 採用ルールの見直し(D-028〜D-032)・正解データ(開発用/検証用)をPR化して `main` にマージ。マージ後に奈良県を再実行(route=actions_direct_v3)。橿原市・斑鳩町の許容URLについてはユーザーから回答なし(未決のまま再実行)。
- 橿原市の `.../kanko_bunka_sports/sports/index.html` は「スポーツ施設より一段上のカテゴリーで、スポーツ施設一覧ではない」(許容しない)。斑鳩町の `category/2-2-0-0-0-0-0-0-0-0.html` は「OK」(許容)。
- 「PRを作ってmainにマージして」(4回目)→ 専用ラベルの確定条件の修正(D-033)と正解データ更新(D-034)をPR化して `main` にマージ。その後 route=actions_direct_v3 で再実行。
- 「crawlを実行した結果を見て」(3回目、見直し版 v3)→ 開発用・検証用で採点し、`docs/reports/pilot-nara-run3.md` に記録。検証用は集計値のみ。
- 「おすすめは?」→ 推奨は A(強いラベルを先に評価・3段目の確認)→ B(新しい検証用)→ C(別の県)→ D(AI判定)の順。「うん、じゃあオススメの順で進めて」(承認)。
- 「正解データ更新したよ」(検証用2)→ 検証用2を記入(10件)。改善A前の結果を集計値のみで採点し `docs/reports/pilot-nara-heldout2-baseline.md` に記録、改善Aの評価基準を事前に記載。
- 「PRを作ってmainにマージして」(5回目)→ 改善A(D-035〜D-037)・検証用2・採点をPR化して `main` にマージ。その後 route=actions_direct_v4 で再実行。
- 「crawlを実行した結果を見て」(4回目、改善A v4)→ 開発用・検証用2(判定)・検証用1(参考)で採点し、`docs/reports/pilot-nara-run4.md` に記録。検証用は集計値のみ。
