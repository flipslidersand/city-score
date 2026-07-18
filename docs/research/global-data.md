# グローバルデータソース調査 (#305)

city-score を将来的に「世界の都市／地域」にも拡張する際の、国際比較データソースの調査。OECD Better Life Index を軸に、代替・補完ソースを整理する。

> 記載は一般に公知の仕様レベル。ライセンス・提供形式は変更され得るため「要検証」項目を参照。

## 1. OECD Better Life Index (BLI)

### 1.1 概要

- 提供元: OECD（経済協力開発機構）
- URL: https://www.oecdbetterlifeindex.org/
- 目的: 「幸福（well-being）」を経済指標（GDP）以外の多次元で測る。city-score の「独自指標（コスト以外の軸）」思想と親和性が高い。

### 1.2 11 の次元（トピック）

Housing / Income / Jobs / Community / Education / Environment / Civic Engagement / Health / Life Satisfaction / Safety / Work-Life Balance。

- 各次元は複数の下位指標から構成（例: Jobs = 雇用率・長期失業率・個人所得・雇用の安定性）。
- 利用者が次元ごとに重みを付けて総合スコアを可視化する設計 → **city-score のライフステージ別／職種別重みづけ機構の先行事例**として参照価値大。

### 1.3 粒度

- **国レベル**（OECD 加盟国 + 一部パートナー国、約 40 か国）。
- 一部次元で**地域（sub-national / OECD Regions）**版あり（後述 Regional Well-Being）。
- **注意**: 都市／市区町村粒度ではない。日本国内の city-score（市区町村粒度）とは粒度が合わないため、**国際「国 or 地域」比較の別レイヤー**として扱う。

### 1.4 取得方法

- BLI 本体: サイトからデータ（Excel）ダウンロードが基本。
- 元指標の多くは **OECD.Stat / OECD Data Explorer**（API あり、後述）から取得可能。

### 1.5 更新頻度

- BLI: 概ね年次更新（更新間隔は年により変動）。**要検証**。

### 1.6 ライセンス

- OECD データは概ね出典明記で再利用可（OECD の利用条件に準拠）。商用利用は条件確認要。**要検証**。

## 2. 補完・代替グローバルソース

| ソース                         | 提供元   | 粒度            | API                       | city-score 用途                                        |
| ------------------------------ | -------- | --------------- | ------------------------- | ------------------------------------------------------ |
| OECD.Stat / OECD Data Explorer | OECD     | 国 / 地域       | SDMX REST API あり        | BLI 元指標、賃金、雇用                                 |
| OECD Regional Well-Being       | OECD     | 地域（TL2/TL3） | データ DL                 | 地域粒度の幸福比較                                     |
| World Bank Open Data           | 世界銀行 | 国（一部都市）  | REST/JSON API（キー不要） | GDP・人口・環境・所得                                  |
| UN Data / UN SDG               | 国連     | 国              | API/DL                    | SDG 系社会指標                                         |
| Eurostat                       | EU       | 国 / NUTS 地域  | REST API                  | 欧州の地域粒度比較                                     |
| Numbeo                         | 民間     | 都市            | 有償 API                  | 生活コスト・治安（**クラウドソース、信頼性は要吟味**） |
| Mercer / EIU Livability        | 民間     | 都市            | 有償レポート              | 駐在員向け住みやすさ（有償）                           |

### 2.1 World Bank API（例）

- ベース: `https://api.worldbank.org/v2/`（JSON 形式は `?format=json`）
- 認証不要。指標コード（例 `NY.GDP.PCAP.CD` = 1 人当たり GDP）+ 国コードで取得。
- 更新: 指標により年次。

### 2.2 OECD SDMX API

- SDMX 標準（統計データ交換規格）。データセット ID + 次元キーで取得。
- フォーマット: SDMX-JSON / XML / CSV。学習コストはやや高い。**要検証**（最新のエンドポイント＝ Data Explorer 移行後の URL 体系）。

## 3. city-score への適用方針

- **粒度の壁**: グローバルは「国 / 地域」、国内は「市区町村」。同一スコア軸で直接比較しない。**別レイヤー（international layer）**として定義し、指標定義書では日本国内を Phase2 の主対象、国際比較を将来拡張と位置づける。
- **指標マッピング**: city-score の 6 指標を BLI 11 次元へ緩くマッピングできる（例: 人生コスト効率 ↔ Income/Housing、社会的孤立 ↔ Community/Life Satisfaction、気候ストレス ↔ Environment）。→ `docs/indicator-spec.md` で相互参照。
- **重みづけ思想の借用**: BLI の「ユーザーが次元重みを操作する」UX は、city-score のライフステージ別／職種別重み機構の直接の参考。

## 4. 要検証項目

- [ ] BLI の更新頻度と最新版年度。**要検証**。
- [ ] OECD データの商用利用条件（city-score が公開/収益化する場合）。**要検証**。
- [ ] OECD Data Explorer 移行後の SDMX API エンドポイント最新形。**要検証**。
- [ ] Numbeo 等民間都市データのライセンス・信頼性（クラウドソースのバイアス）。**要検証**。
- [ ] 国／地域粒度 → 都市粒度の対応が必要になった際の代替（都市データは民間有償が中心）。**要検証**。
