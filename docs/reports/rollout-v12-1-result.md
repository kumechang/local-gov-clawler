# v12.1 同点のタイブレーク: 結果

事前基準は `rollout-v12-1-plan.md`。判定ルールだけの変更なので、保存済みの結果から判定をやり直した(`redecide`、route=`redecide_v12_1`、サイトには接続していない)。対象は v12 の1,747件(政令市の区を除く)。

## 事前基準の判定

1. **退行ゼロ**: 達成。v12で hub_selected だった自治体の確定URLは、1件も変わっていない。
2. **正解データ21件**: 達成。確定した件数 6→10、正解 5→9、誤り 1→1(堺市。従来の誤りのまま)。
3. **代表8件**: 達成。出雲市・一宮市・太良町・読谷村が、正解で確定した(日の出町・松江市・安中市・北杜市は、規則の対象外で同点のまま)。
4. **効果**: hub_multiple 169→136(33件が hub_selected に。確定 738→771、全国で 42.2%→44.1%)。
5. **新しい確定の精度**: ユーザーの判断待ち(10件、`data/review/v12_1/spotcheck.md`)。

## 最初の実行での修正(結果を見たあとの変更。記録として残す)
最初の実行(33件、規則の内訳 T1 10・T2 14・T3 8・T4 1)の確定を目で見て、次の3つの誤りの型を見つけたので、規則を狭めて実行し直した。
- T1が複合ラベル『文化・スポーツ施設 -連絡先一覧-』(栄町)を選んだ → T1の対象を sports_pure/sports_other に限定
- T3が、分類ページ(『公園・スポーツ施設』など、釧路市・横手市・清須市)や、同じページが http/https で二重になった同点(大磯町)の親を採ってしまった → T3は、同点の上位2件がどちらも1つの施設の名前のときだけ。同じページ(scheme等の違い)は候補を1件にまとめる
- 退行ゼロ、正解データ(21件)の結果は、最初の実行と同じ。

## 新しく確定した33件(規則の内訳 T1 9・T2 または同じページの統合 20・T3 3・T4 1)

| 規則 | コード | 自治体 | 確定したページ | 施設数 |
|---|---|---|---|---|
| T1 | 06428 | 庄内町 | 町内体育施設 一覧 https://www.town.shonai.lg.jp/sportskouen/shisetsu/ichiran.html | 6 |
| T1 | 08203 | 土浦市 | 体育施設一覧 https://www.city.tsuchiura.lg.jp/kurashi-tetsuzuki/kokyoshisetsu/taiikushisetsu/ | 13 |
| T1 | 10208 | 渋川市 | スポーツ施設一覧 http://www.city.shibukawa.lg.jp/kyouiku/000144/000148/p001549.html | 66 |
| T1 | 11207 | 秩父市 | スポーツ施設一覧 https://www.city.chichibu.lg.jp/dd.aspx?menuid=1179 | 2 |
| T1 | 18501 | 若狭町 | 体育施設の一覧 https://www.town.fukui-wakasa.lg.jp/shisetsuosagasu/1201.html | 5 |
| T1 | 27228 | 泉南市 | スポーツ施設・公園一覧 https://www.city.sennan.lg.jp/kanko/1458795189336.html | 6 |
| T1 | 32203 | 出雲市 | スポーツ施設一覧 https://www.city.izumo.shimane.jp/www/contents/1115027917001/index.html | 33 |
| T1 | 35201 | 下関市 | スポーツ施設一覧 https://www.city.shimonoseki.lg.jp/soshiki/66/3725.html | 42 |
| T1 | 38201 | 松山市 | 松山市公共スポーツ施設一覧 https://www.city.matsuyama.ehime.jp/shisetsu/koen/sportssyoukai/sportsshisetsu/sisetuichiran.html | 5 |
| T2/dedupe | 01333 | 知内町 | スポーツ施設 https://www.town.shiriuchi.hokkaido.jp/about/shisetsu/sports/ | 5 |
| T2/dedupe | 01343 | 鹿部町 | スポーツ https://www.town.shikabe.lg.jp/kanko_bunka_sports/sports/index.html | 4 |
| T2/dedupe | 01428 | 長沼町 | スポーツ施設 https://www.maoi-net.jp/kosodate_kyoiku/sports/sportsshisetsu/ | 7 |
| T2/dedupe | 01484 | 羽幌町 | スポーツ施設 https://www.town.haboro.lg.jp/shisetsu/sports/index.html | 6 |
| T2/dedupe | 03321 | 紫波町 | スポーツ https://www.town.shiwa.iwate.jp/soshiki/5_1/2_3/ | 2 |
| T2/dedupe | 06403 | 飯豊町 | スポーツ https://www.town.iide.yamagata.jp/kyouikutobunka/sport/index.html | 4 |
| T2/dedupe | 10212 | みどり市 | スポーツ・レクリエーション施設 https://www.city.midori.gunma.jp/shisetsu/1001688/index.html | 15 |
| T2/dedupe | 12204 | 船橋市 | スポーツ施設 https://www.city.funabashi.lg.jp/shisetsu/sportsshisetu/index.html | 2 |
| T2/dedupe | 12227 | 浦安市 | スポーツ施設 https://www.city.urayasu.lg.jp/shisetsu/sports/index.html | 6 |
| T2/dedupe | 13101 | 千代田区 | スポーツ https://www.city.chiyoda.lg.jp/koho/bunka/sports/index.html | 4 |
| T2/dedupe | 13102 | 中央区 | スポーツ https://www.city.chuo.lg.jp/bunkakankou/sports/index.html | 6 |
| T2/dedupe | 13201 | 八王子市 | スポーツ施設 https://www.city.hachioji.tokyo.jp/shisetsu/004/index.html | 2 |
| T2/dedupe | 13363 | 新島村 | スポーツ施設 https://www.niijima.com/facility/sports/ | 2 |
| T2/dedupe | 20204 | 岡谷市 | スポーツ https://www.city.okaya.lg.jp/bunka_sports/sports/index.html | 3 |
| T2/dedupe | 22208 | 伊東市 | スポーツ施設 https://www.city.ito.shizuoka.jp/gyosei/bunka_sports/sports/sportsshisetsu/index.html | 3 |
| T2/dedupe | 23203 | 一宮市 | スポーツ施設 https://www.city.ichinomiya.aichi.jp/shisetsu/1008918/index.html | 4 |
| T2/dedupe | 23235 | 弥富市 | スポーツ施設 https://www.city.yatomi.lg.jp/shisetsu/1000993/index.html | 3 |
| T2/dedupe | 40621 | 苅田町 | スポーツ https://www.town.kanda.lg.jp/life/4/19/ | 2 |
| T2/dedupe | 44202 | 別府市 | スポーツ施設 https://www.city.beppu.oita.jp/sisetu/supootu/index.html | 18 |
| T2/dedupe | 45202 | 都城市 | スポーツ https://www.city.miyakonojo.miyazaki.jp/life/6/75/ | 7 |
| T3 | 01233 | 伊達市 | 施設情報 https://www.city.date.hokkaido.jp/hotnews/category/159.html | 7 |
| T3 | 41208 | 小城市 | 小城市:公共施設案内 公共施設案内 https://www.city.ogi.lg.jp/main/11170.html | 10 |
| T3 | 41441 | 太良町 | 公共施設利用案内 https://www.town.tara.lg.jp/koukyou.html | 10 |
| T4 | 47324 | 読谷村 | 読谷村体育施設 https://www.vill.yomitan.okinawa.jp/gyosei_joho/shisetsu/taiikushisetsu/index.html | 4 |

## 残る同点(136件)
日の出町・松江市・安中市・北杜市のように、『どれでもOK』の同点が含まれる。次は、(1) 残りの型の代表を判断する、(2) 同点でも先頭を選んでよい型(同じ種類の一覧が複数ある)を『確定』と扱うか決める、のどちらか。

## 事前基準5の判定: ユーザーの確認10件(2026-10-16)と、その後の変更(D-105)
| 規則 | 件数 | 妥当 | 不適切 | 要判断 |
|---|---|---|---|---|
| T1 一覧 | 3 | 庄内町・泉南市 | | 秩父市(『この先のPDFに一覧がある』。確定したページは一覧そのものではなく、PDFへの入口) |
| T2 親 | 5 | 紫波町・八王子市・船橋市 | 千代田区(正解は `/shisetsu/bunka/index.html`)・岡谷市(正解は `/soshikikarasagasu/sportsshinkoka/438/3526.html`) | |
| T3 汎用の親 | 2 | 伊達市・小城市 | | |

- 誤りが2割を超えた規則: **T2(2/5=40%)**。誤りの2件はどちらも『スポーツ』だけのラベルで、妥当な3件のうち2件は『スポーツ施設』(紫波町の『スポーツ』は妥当)。そこで T2 を、強いラベル(スポーツ施設・体育施設・運動施設)の親だけに**狭めた**。標本が小さいので、狭めた形の検証はこれからの確認で行う。
- T1: 秩父市を誤りに数えると 1/3 で2割を超えるが、確定したページは『スポーツ施設一覧』という一覧の入口で、完全な誤りとは言い切れないので、T1は残した(ユーザーが異論なら取り下げる)。出雲市(正解データ)を含めると 3/4 が妥当。
- T3: 2/2 妥当。そのまま。

### 狭めたあとの結果(`redecide_v12_1` を作り直し)
- 退行ゼロ(v12で確定していた自治体のURLは変わらない)。
- hub_multiple 169→144、hub_selected 738→763(25件)。
- 正解データ30件(ユーザー判断を9件追加): 到達27、確定 6→16、正解 5→15、誤り 1→1(堺市)。
- 上の33件の一覧のうち、『スポーツ』だけの親(T2)で選ばれていた8件(千代田区・岡谷市・紫波町・鹿部町・飯豊町 など)は同点に戻った。
