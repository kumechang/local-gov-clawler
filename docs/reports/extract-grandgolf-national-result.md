# 施設詳細の取り出し 全国(グラウンドゴルフ)の結果

実行: 47都道府県(`national_*`)、対象は『場所』と判定されたページ 1,421。取り出しはルールだけ(AIなし、D-050)。

## 事前基準との比較
| 項目 | 基準 | 結果 | 判定 |
|---|---|---|---|
| ページの取得 | 95%以上 | 1,418/1,418 = 100%(自治体1件は robots 到達不可) | 達成 |
| 住所あり(行) | 60%以上 | 55.7% | **わずかに未達** |
| 電話あり(施設の電話か問い合わせ先の電話) | 90%以上 | 88.3% | **わずかに未達** |
| 取得ルール(robots・1秒・ログイン無し) | 破らない | 違反0 | 達成 |
| 住所・電話・施設名の正しさ(ユーザーの15行確認) | 9割以上 | 確認待ち | — |

## 行数(絞り込み後)
1,554行(404自治体)。住所あり 865、施設の電話あり 1,149、問い合わせ先の電話あり 937。取り出し元は kv 535・表の行 500・本文 438・kv+本文の電話 76・なし 5。

## 絞り込み(D-128)
取り出し直後は 2,045行(住所44.5%)。ページ端のバナー広告・おすすめ・『電話・FAX』・料金表の数字の行が混ざっていたため、**書き出し時に**絞り込む(`keep_item`)。取り込みの結果(`data/extract/`)は変えていない。さらに15行の確認で見つけた細かい欠陥(住所末尾の括弧、サイト名が施設名になる、問い合わせ先に法人番号の欄、『お問合せ』が名前になる)を書き出し時に直した。
- 都道府県別の個別CSV(`data/export/by_run/`)は絞り込み前のもの。**全国の `data/export/grandgolf_places_detail.csv` が最新**。

## 住所が低い理由
- 本文からの取り出し(text)は住所30%と弱い。表(65%)・見出し+値(63%)は高い。
- 住所の無い行の多くは、実在の施設で電話はあるが、ページに住所が書かれていない(例: 志賀町多目的スポーツセンター、水戸市総合運動公園)。

## 確認用15行(都道府県をばらして抽出、うち3行は住所なし)
| # | 自治体 | 施設名 | 住所 | 施設の電話 | 問い合わせ先 | ページ |
|---|---|---|---|---|---|---|
| 1 | 滋賀県大津市 | 和邇市民運動広場(グラウンド・テニスコート) | 大津市和邇今宿851 | 077-594-8022 | — | https://www.city.otsu.lg.jp/sc/s/sh/g/67747.html |
| 2 | 秋田県三種町 | 八竜体育施設 | 秋田県山本郡三種町鵜川字西本田65-1 | 0185-85-2930 | 0185-87-2222 | http://www.town.mitane.akita.jp/kanko_bunka_sports/sports/sportsfacilities/3469.html |
| 3 | 熊本県嘉島町 | 金畑公園 | 嘉島町上六嘉2399番地1 | 096-237-2597 | 096-237-1111 | https://www.town.kumamoto-kashima.lg.jp/q/aview/253/547.html |
| 4 | 鹿児島県霧島市 | 郡山地区コミュニティ広場 | 霧島市国分郡田1211 | 0995-64-0921 | — | https://www.city-kirishima.jp/ken-cho/shisetsu/kosodate-koen/115.html |
| 5 | 福井県福井市 | 日野川浄化センター芝生広場 | — | 0776-26-5701 | — | https://www.city.fukui.lg.jp/kurasi/gesui/sisetu/gpark.html |
| 6 | 茨城県五霞町 | 丸池台グラウンド・ゴルフ場 | 茨城県猿島郡五霞町元栗橋2847-1 | 0280-84-3533 | 教育委員会 スポーツ振興係 0280-84-3533 | https://www.town.goka.lg.jp/kurashi-machi-shigoto/gokanabi/sports/kaiyou/page006301.html |
| 7 | 宮崎県小林市 | 大塚原運動広場 | 宮崎県小林市野尻町三ヶ野山4336 | 0984-44-1100 | 野尻庁舎 地域振興課 0984-44-1100 | https://www.city.kobayashi.lg.jp/kanko_bunka_sports/sports/sportsshisetsu/3435.html |
| 8 | 宮城県亘理町 | SAKANアスリートパーク鳥の海多目的広場(鳥の海公園多目的広場) | 亘理町荒浜字築港通り9番地2 | — | — | https://www.town.watari.miyagi.jp/detail.php?content=2102 |
| 9 | 青森県中泊町 | 体育センター | — | 0173-57-2111 | 青森県北津軽郡中泊町大字中里字紅葉坂209番地 中泊町教育委員会 0173-57-2111 | https://www.town.nakadomari.lg.jp/soshikikarasagasu/kyoikuiinkai/supo-tu/1/1/1380.html |
| 10 | 石川県かほく市 | スポーツ・レジャー施設 | — | 076-283-1111 | — | https://www.city.kahoku.lg.jp/shisetu/080/index.html |
| 11 | 長野県佐久市 | 佐久地域定住自立圏 スポーツ施設(市町村別) | 長野県佐久市中込3056 | 0267-62-4004 | — | https://www.city.saku.nagano.jp/shisetsu/teijujiritsuken/sports_shichosom.html |
| 12 | 和歌山県和歌山市 | 和歌山市つつじが丘総合公園中央公園ゾーン(多目的球技場他) | 和歌山市つつじが丘4丁目5番 | 073-488-5702 | 産業交流局 文化スポーツ部 スポーツ振興課 073-435-1364 | https://www.city.wakayama.wakayama.jp/shisetsu/kouen_sp_shisetsu/1006086/1060590.html |
| 13 | 静岡県川根本町 | 生涯スポーツ広場 | 川根本町上岸11-5地先 | 0547-59-3332 | 社会教育課 社会教育室 0547-58-7080 | https://www.town.kawanehon.shizuoka.jp/shisetsu/2/918.html |
| 14 | 島根県出雲市 | 一の谷公園 | 今市町2010-1 | — | — | https://www.city.izumo.shimane.jp/www/contents/1115027917001/index.html |
| 15 | 北海道室蘭市 | 宿泊研修施設(サンパワー380) | — | 0143-25-2574 | 0143-25-2574 | https://www.city.muroran.lg.jp/administration/?content=619 |

気になる点: #9 問い合わせ先に住所が混ざる(中泊町)、#10 施設名が分類名(かほく市)、#11 施設名がページ名(佐久市)。
記入用: `data/ground_truth/extract_grandgolf_national_sample.csv`
