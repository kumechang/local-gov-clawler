# 正解データ(目視確認)

受け入れテスト(ハブページ到達率)の基準。自治体のサイトを人が見て、
「スポーツ施設(体育施設・公共グラウンド)の一覧に最も近い入口ページ」のURLを記入する。

- `sports_hub_nara.csv` に10件程度記入する(列: `municipality_code,hub_url,notes`)
- 評価: `localgov-crawler evaluate --route <route> --truth data/ground_truth/sports_hub_nara.csv`
- 「到達」の定義: 正解URLが、そのクローラー結果のハブ候補上位5件(`genre_entrypoints[].candidates`)に含まれること
  (末尾スラッシュとフラグメントの違いは無視)
- 自治体にそのような入口ページが無い場合は `hub_url` を空にせず、行自体を作らない(受け入れテストの母数に含めない)
