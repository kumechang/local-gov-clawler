# 手動確認リスト

`data/review/v11/<都道府県コード>_<都道府県>.csv`: v11 で確定できなかった自治体(1,020件)。`localgov-crawler review-list <route…>` で生成(D-092)。

## 列
- `municipality_code, municipality_name, official_url, outcome, failure_class`
- `cand1〜cand5_*`: クローラーが見つけた上位5件の候補(文言・URL・種類・スコア・施設数)。正解が入っていることが多い
- **`reviewed_hub_url`**: 人が記入する欄。スポーツ施設が並ぶ、トップに最も近いページのURL。ないときは『なし』
- `note`: メモ

## 使い方
1. 自治体のサイトで「スポーツ施設」の一覧を探す(候補のURLを先に見ると早い)
2. `reviewed_hub_url` に記入
3. 記入済みのCSVをコミット/共有 → 正解データ(`data/ground_truth/`)に取り込み、ルールの検証(特に同点のタイブレーク)に使う。AIは使わない(D-050)
