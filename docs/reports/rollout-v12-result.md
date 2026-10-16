# v12の結果(全国1,747件、v11との差分)

実行: auto-crawl run 38857347091(PR #18 のマージ)/ 結果は `data/results/actions_direct_v12_<ローマ字>/`。
事前基準: `docs/reports/rollout-v12-plan.md`(結果を見る前に記録)。

## 結論
**事前基準5項目のうち、4つは達成、1つ(確認用12件の確定した誤りが0件)は未達成。計画どおり、v11を全国の最新版のままにする。** 本文の短い行を数える変更は、確定を23件増やしたが、取りこぼし145件のうち効いたのは一部だけで、すでに誤りと判断済みの堺市が再び誤確定された。

## 事前基準の判定
| # | 項目 | 結果 | 判定 |
|---|---|---|---|
| 1 | 正解データの回帰(奈良・福井の6つ) | 確定して正解27件・精度27/28=96%(v11と同じ。6つとも件数が同一) | 達成 |
| 2 | 確認用12件(ユーザー判断済み)の確定した誤り | 4件正解は維持。**堺市が再び誤確定**: 『スポーツ』(`sports/index.html`)を確定した。ユーザーが誤りと判断した(正解は2階層下の `sports_shisetsu/shisetsu/index.html`)ページ。本文の『・原池公園野球場』『・大浜体育館』のような行(寄附のお願いの文中の箇条書き)を施設として数えたため | **未達成** |
| 3 | v11で確定していた722件の変化 | 13件(1.8%): 確定が外れた8件(同点で `hub_multiple` に)・ページが変わった5件 | 達成 |
| 4 | 新しく確定した自治体の質 | 23件。題名と施設の例から『一覧でなさそう』なのは3件(13%): 堺市(誤りと判断済み)、上島町(『弓削体育館』と『・2F競技場』など、1つの体育館の中の部屋)、あさぎり町(『免田地区体育施設』、1つの地区の施設) | 達成(基準15%以下) |
| 5 | 取得面 | 失敗・ブロック18件(v11は17件)、平均リクエスト数10.8(v11は10.8)、平均24.9KB(合計43.4MB) | 達成 |

## 数字
- 確定: v11 722件 → v12 737件(新しく確定23、外れた8、ページが変わった5)
- `hub_multiple`: 167 → 169、`hub_not_found`: 794 → 776
- 取りこぼし145件(専用ラベルのページを取得したが施設が取れない・本文に施設語が5以上)のうち、確定したのは約23件(16%)。残りは、施設語が文や表の中にあってこの方法では取れない、一覧が別のページにある、などと考えられる

## 差分の全件
### 新しく確定した23件(v11は未確定)

| 自治体 | 確定したページ | URL | 施設の例 |
|---|---|---|---|
| 日高町 | 社会教育・社会体育施設(composite・4件) | http://www.town.wakayama-hidaka.lg.jp/docs/2014090800318/ | 比井崎体育館、備考:体育館、武道館 |
| 女川町 | 社会教育施設・スポーツ施設についてはこちら(composite・10件) | https://www.town.onagawa.miyagi.jp/05_16_00_02.html | 体育室和室調理実習室集会、グラウンド、柔道場 |
| 長生村 | 体育施設(pure・6件) | https://www.vill.chosei.chiba.jp/0000000234.html | 長生村体育館、長生村武道館、概要:剣道場、柔道場 |
| 上島町 | スポーツ施設(pure・4件) | https://www.town.kamijima.lg.jp/site/publicfacilities/694.html | >上島町弓削体育館、上島町弓削体育館、・競技場 |
| おいらせ町 | スポーツ施設(pure・7件) | https://www.town.oirase.aomori.jp/soshiki/2220/sportsshisetsu.html | 電話番号:0178-52、体育館、テニスコート |
| 毛呂山町 | 体育施設(pure・2件) | https://www.town.moroyama.saitama.jp/gyoseisite/manabi_bunka_sports/bunka_sportsshisetsu/3/4442.html | 大類グラウンド、毛呂山総合公園体育館 |
| 皆野町 | スポーツ施設(pure・6件) | https://www.town.minano.saitama.jp/chouei/sports/ | 皆野町弓道場、皆野スポーツ公園、皆野町運動公園 |
| 大樹町 | 体育施設(pure・6件) | https://www.town.taiki.hokkaido.jp/choseijoho/taikichonitsuite/3/sports-shisetu/1636.html | 大樹町B&G海洋センター、大樹町武道館、大樹中央運動公園 |
| 北竜町 | 社会教育・体育施設(composite・4件) | https://www.town.hokuryu.hokkaido.jp/kosodate/taiiku-shiseitsu/ | 体育館、北竜町営野球場、北竜町B&G海洋センター |
| 幌延町 | スポーツ/レクリエーション施設(pure・8件) | https://www.town.horonobe.lg.jp/www4/section/edu/le009f0000000dwg.html | 総合体育館・町民プール、総合スポーツ公園、パークゴルフ場 |
| 下川町 | 下川町文化施設・体育施設のご案内一覧表(composite・10件) | https://www.town.shimokawa.hokkaido.jp/section/2020/01/post-229.html | 第1ホール第2ホール柔道、グランド、プール |
| 千歳市 | 体育施設(pure・4件) | https://www.city.chitose.lg.jp/c40/1002688/1002690/1005308.html | 公益財団法人千歳市スポー、スポーツセンター(ダイナ、温水プール |
| 矢吹町 | スポーツ施設(pure・5件) | https://www.town.yabuki.fukushima.jp/page/page002041.html | 勤労者体育館・テニスコー、温水プール、屋内ゲートボール場 |
| 北塩原村 | 体育施設(pure・3件) | https://www.vill.kitashiobara.fukushima.jp/soshiki/somukikaku/3100.html | 北塩原村民体育館、北塩原村民運動場、スポーツパーク |
| 和木町 | スポーツ施設(pure・4件) | https://www.town.waki.lg.jp/site/kyoiku/479.html | ※体育センター・庭球場、和木町体育センター、庭球場 |
| あさぎり町 | 免田地区体育施設(あさぎり町生涯学習センター内)(composite・9件) | https://www.town.asagiri.lg.jp/kiji003160/index.html | 体育館、多目的グラウンド、武道館 |
| うるま市 | スポーツ施設案内(pure・18件) | https://www.city.uruma.lg.jp/1007004000/contents/740.html | 総合アリーナ、うるま市具志川総合体育館、うるま市具志川総合グラウ |
| 宮古島市 | スポーツ施設(pure・6件) | https://www.city.miyakojima.lg.jp/soshiki/kyouiku/syougaigakusyu/sports/ | 体育館、旧砂川中学校運動場、旧砂川中学校体育館 |
| 吉賀町 | スポーツ施設(pure・9件) | https://www.town.yoshika.lg.jp/kurashi/kyouiku/supotsushisetsu/supotsu.html | 吉賀町スポーツ公園、スポーツ公園、吉賀町真田グラウンド |
| 白石町 | スポーツ施設(pure・16件) | https://www.town.shiroishi.lg.jp/jyuumin/shisetsu/_1743.html | しろいしパークゴルフ場、白石中央公園テニスコート、白石社会体育館 |
| 真室川町 | 社会教育施設・社会体育施設(composite・10件) | https://www.town.mamurogawa.yamagata.jp/kurashi_tetsuzuki/shogai/1901.html | 町民ターゲットバードゴル、町民グラウンドゴルフ場、町民体育館 |
| 北相木村 | スポーツ施設(pure・3件) | http://www.vill.kitaaiki.nagano.jp/docs/287.html | アリーナ(体育館、グリーンドーム(北相木村、マレットゴルフ(北相木マ |
| 堺市 | スポーツ(pure・3件) | https://www.city.sakai.lg.jp/kurashi/sports/index.html | ・原池公園野球場、・大浜体育館、金岡公園のスポーツ施設等 |

### v11で確定していたが同点で確定しなくなった8件

| 自治体 | v11の確定ページ | URL |
|---|---|---|
| 栄町 | 文化・スポーツ施設 -連絡先一覧- | https://www.town.sakae.chiba.jp/kurashi/shisetsu/page000326.html |
| 鴨川市 | スポーツ施設 | https://www.city.kamogawa.lg.jp/life/1/11/59/ |
| 伊東市 | スポーツ施設 | https://www.city.ito.shizuoka.jp/gyosei/bunka_sports/sports/sportsshisetsu/index.html |
| 清須市 | 社会体育施設 | https://www.city.kiyosu.aichi.jp/shisetsu_annai/shakitaiiku_shisetsu/index.html |
| あま市 | 体育館 | https://www.city.ama.aichi.jp/shisetsu/1004201/1004583/index.html |
| 新見市 | 主な公共体育施設 | https://www.city.niimi.okayama.jp/kurashi/kurashi_detail/index/20 |
| 清里町 | スポーツ | https://www.town.kiyosato.hokkaido.jp/education/?category=43 |
| 沖縄市 | スポーツ施設 | https://www.city.okinawa.okinawa.jp/shiseijouhou/gaiyou/shisetsu/shisetsuannai/sportsshisetsu/index.html |

### 確定ページが変わった5件

| 自治体 | v11 | v12 |
|---|---|---|
| 設楽町 | 公園・スポーツ施設 https://www.town.shitara.lg.jp/life/4/40/225/ | スポーツ施設一覧 https://www.town.shitara.lg.jp/soshiki/13/1234.html |
| 三笠市 | スポーツ https://www.city.mikasa.hokkaido.jp/hotnews/category/103.html | スポーツ施設 https://www.city.mikasa.hokkaido.jp/hotnews/detail/00005507.html |
| 浜中町 | 社会体育施設の使用について https://www.townhamanaka.jp/kakuka/kyouikuiinkaisyougaigakusyuka/sports/sinseisyosetumei-0424.html | スポーツ施設 https://www.townhamanaka.jp/kurashi_kankyou/shisetu/sports/ |
| 竹田市 | 学び・スポーツ Learning https://www.city.taketa.oita.jp/manabi_sports/index.html | 学校体育施設(市内小学校・中学校 https://www.city.taketa.oita.jp/manabi_sports/supo-tsushinkou/12694.html |
| 池田町 | スポーツ施設 https://www.ikedamachi.net/category/2-15-4-4-0-0-0-0-0-0.html | スポーツ施設 https://www.ikedamachi.net/0000000852.html |

## 考察と次の案(v11を最新版のまま、変更は保留)
1. **本文の短い行を数える方式は、効くが小さい**。確定23件のうち約20件は、施設が並ぶページに見える(おいらせ町・皆野町・大樹町・幌延町・矢吹町・和木町・うるま市・宮古島市・吉賀町・白石町など)。ただし堺市のような、箇条書きの文中の施設名を一覧と誤る型がある
2. 改善案(v12.1): 本文の行だけで施設を数えるときは、明確に『リスト』と言える件数(4件以上)を求める。堺市(3件)は外れる。北相木村・北塩原村(3件)も外れる。または、寄附・建替・整備の語を含むページでは本文の行を数えない
3. **同点で確定しなくなった8件**(栄町・鴨川市・伊東市・清須市・あま市・新見市・清里町・沖縄市)は、v11の確定が正しかったかを、ユーザーの手動確認で判断できる(上の表のURL)。正しければ、同点のタイブレークを入れる根拠になる
4. 次は、手動確認リスト(`data/review/v11/`)の記入結果を使って、同点のタイブレークと v12.1 を決めるのが、データに基づいて最も確実
