# 手動確認: まず代表8件(同点 `hub_multiple` の型ごと)

同点167件(v11の手動確認リスト)を、候補の型で分けた。型ごとに1〜2件を選んだ。
**8件の判断で、残りの同点にあてはまるルールを決める**(AIは使わない、D-050)。

回答の形: 各自治体について「候補の番号」「別のURL」「どれでもない(なし)」のどれか。
判断の理由が一言あると、ルールにしやすい(例: 『一覧という語があるほう』『親のページ』)。

## 1. 出雲市(32203): 一覧という名前 vs 分類ページ(pure同士、型A 53件)
1. スポーツ施設一覧 https://www.city.izumo.shimane.jp/www/contents/1115027917001/index.html (施設25)
2. スポーツ施設 https://www.city.izumo.shimane.jp/www/genre/1000000000054/index.html (施設20)
3. スポーツ施設 https://www.city.izumo.shimane.jp/www/genre/1703234530837/index.html (施設21)
- 知りたいこと: 名前に『一覧』があるほうを優先してよいか。施設数の多いほうでよいか。

## 2. 日の出町(13305): 体育施設 vs スポーツ施設(pure同士、別の分類の下)
1. 体育施設 https://www.town.hinode.tokyo.jp/category/1-8-8-4-0-0-0-0-0-0.html (施設5)
2. スポーツ施設 https://www.town.hinode.tokyo.jp/category/3-5-3-0-0-0-0-0-0-0.html (施設4)
- 知りたいこと: 同じ種類の一覧が2つあるとき、どちらでもよいか(両方正解か)。片方なら、何が決め手か。

## 3. 松江市(32201): pureの分類 vs 『一覧』という名前のページ(型B 29件)
1. 運動施設 https://www.city.matsue.lg.jp/kanko_bunka_sports/sports/3/index.html (施設16)
2. スポーツ施設一覧(地区分け) https://www.city.matsue.lg.jp/shisetsuwosagasu/12074.html (施設16)
3. スポーツ施設の紹介 https://www.city.matsue.lg.jp/kanko_bunka_sports/sports/9844.html (施設16)
- 知りたいこと: 『一覧』という語を持つページが、分類ページに勝つか。トップに近いほう(階層)を優先するか。

## 4. 安中市(10211): 広い『スポーツ』vs 『公園・スポーツ施設』(型B)
1. スポーツ https://www.city.annaka.lg.jp/life/1/11/52/ (施設9)
2. 公園・スポーツ施設 https://www.city.annaka.lg.jp/life/6/37/174/ (施設9、スコアは2のほうが高い)
3. 安中地域スポーツ施設-グラウンド- https://www.city.annaka.lg.jp/page/2390.html (施設3)
- 知りたいこと: 『スポーツ』(行事や団体も含む広い入口)と『公園・スポーツ施設』(施設中心)のどちらが一覧か。

## 5. 一宮市(23203): 親と子(型C 12件)
1. スポーツ施設 https://www.city.ichinomiya.aichi.jp/shisetsu/1008918/index.html (親、施設4)
2. 屋内スポーツ施設 https://www.city.ichinomiya.aichi.jp/shisetsu/1008918/1044559/index.html (子、施設7)
3. スポーツ施設(中学校・小学校) https://www.city.ichinomiya.aichi.jp/shisetsu/1008918/1044561/index.html (子、施設4)
- 知りたいこと: 親(トップに近い)と、子(屋内・屋外などの分類)のどちらを一覧とするか。刈谷市(親=妥当)と同じ扱いでよいか。

## 6. 北杜市(19209): 町ごとに別々の案内(型D、other同士 35件)
1. 大泉町 社会体育・スポーツ施設利用案内 https://www.city.hokuto.yamanashi.jp/docs/1510.html (施設4)
2. 白州町 社会体育・スポーツ施設利用案内 https://www.city.hokuto.yamanashi.jp/docs/1492.html (施設2)
3. 武川町 社会体育・スポーツ施設利用案内 https://www.city.hokuto.yamanashi.jp/docs/1685.html (施設2)
- 知りたいこと: 市全体の一覧が別にあるか(あればそのURL)。無ければ『なし』。地区ごとに分かれている自治体は、一覧『なし』としてよいか。

## 7. 太良町(41441): 個別の施設ページ同士(型D)
1. B&G海洋センター体育館 https://www.town.tara.lg.jp/koukyou/_1322.html
2. B&G海洋センター第2体育館 https://www.town.tara.lg.jp/koukyou/_1331.html
3. 公共施設利用案内 https://www.town.tara.lg.jp/koukyou.html (施設10)
- 知りたいこと: 個別の施設ページが並ぶとき、その上の『公共施設利用案内』(スポーツ以外の施設も含む)を一覧としてよいか。

## 8. 読谷村(47324): 利用案内のpage vs 『読谷村体育施設』(型E、composite対other)
1. 社会体育施設・学校体育施設の利用について https://www.vill.yomitan.okinawa.jp/kanko_bunka_sports/sports/2643.html (施設7)
2. 読谷村体育施設 https://www.vill.yomitan.okinawa.jp/gyosei_joho/shisetsu/taiikushisetsu/index.html (施設4)
3. 公共施設一覧 https://www.vill.yomitan.okinawa.jp/gyosei_joho/shisetsu/3917.html (施設4)
- 知りたいこと: 『利用について』(案内文)より、施設名がそのまま並ぶページを優先するか。

## 記入先
回答は会話で伝えてもらえればよい(私が `reviewed_hub_url` に転記して、正解データに追加する)。
