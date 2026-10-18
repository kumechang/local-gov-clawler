# グラウンドゴルフの調査結果(CSV)

`localgov-crawler survey-export --keyword grandgolf --routes-file config/survey_sets/grandgolf.json` で作成(元データは `data/survey/grandgolf/`)。
ワードの有無を調べた結果から、**ワードのあったページ1件を1行**にして、種類ごとに分けている。

| ファイル | 内容 | 行数(自治体数) |
|---|---|---|
| `grandgolf_places.csv` | **場所**: 施設・公園・グラウンド・体育館などの紹介ページ | 1,421(487) |
| `grandgolf_events.csv` | **イベント**: 大会・教室・フェスタ・参加者募集などのページ | 419(208) |
| `grandgolf_others.csv` | その他: 協会・クラブ・団体の紹介、用具の貸出、補助金、お知らせ、手続きなど | 608(355) |

全国1,747自治体(政令市の区を除く)のうち、ワードがあった701自治体がいずれかに入る。1つの自治体が複数のファイルに入ることがある。

## 列
- `prefecture, municipality_code, municipality_name`: 都道府県、自治体コード、自治体名
- `page_kind`: ページの種類。題名から判断(facility=場所 / event=イベント / organization=団体・クラブ / other=その他)。**題名による目安で、ページの中身を厳密に分類したものではない**(例: 公園の紹介が『その他』になることがある)
- `page_title, page_url`: ページの題名とURL
- `matched_text`: ワードの前後の短い文(最大3つ、` / ` 区切り)。ページ本文の転載ではなく、見つけた箇所の確認用
- `match_count`: ページ内のワードの数、`in_title`: 題名にワードがあるとき1
- `found_via, via_link_text`: そのページに行き着いた経路(listing=スポーツ施設の一覧、facility=施設のページ、event=イベントの入口、sports_nav / broad=別の入口)と、たどったリンクの文言
- `site_url`: 自治体の公式サイト、`survey_route, surveyed_at`: 調査の実行(route)と終了日時(UTC)

## 注意
- 『ワードなし』は『その自治体にない』ではなく、**調べた範囲(入口から2階層、1自治体200ページまで)にワードが見つからなかった**という意味。入口が見つからない自治体(57件)・取得できなかった自治体(18件)は調べられていない(`data/summary/survey_grandgolf_national.csv`)。
- PDFの中身は読んでいない。ワードがあるのはHTMLのページだけ。
- 否定の記載(『グラウンド・ゴルフではご利用いただけません』など)は除いている(`docs/decisions.md` D-113, D-116, D-119, D-122)。
- 愛知県・福井県は、別の入口とヘッドレス取得が入る前の結果。
