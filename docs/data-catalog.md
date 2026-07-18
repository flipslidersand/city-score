# Phase 1 データカタログ (#306)

city-score が使用する（予定の）データを一覧化した台帳。機械可読版は [`data-sources.csv`](./data-sources.csv) と**同期**して管理する。CSV が正、本ファイルは人間可読な解説を付す。

> 「推定欠損率」は現時点の見込みであり実測値ではない。実データ取得後に更新する（**要検証**）。

## 1. 粒度・キー方針

- **正規化キー**: `area_code`（市区町村 5 桁 JIS コード） × `year`。
- 市区町村より粗い粒度（都道府県 / 医療圏 / 観測所 / GIS）は、按分・継承・空間結合で市区町村へ近似し、近似手法を `notes` に記録。
- 国際データ（OECD BLI 等）は市区町村と非連結の**別レイヤー**。

## 2. 列定義（CSV スキーマ）

| 列名                     | 意味                                | 例                                                   |
| ------------------------ | ----------------------------------- | ---------------------------------------------------- |
| `indicator`              | 指標の内部 ID（snake_case）         | `job_offer_ratio`                                    |
| `source`                 | 具体的な統計表・調査名              | `厚労省 一般職業紹介状況`                            |
| `provider`               | 提供機関                            | `厚生労働省`                                         |
| `granularity`            | 元データの粒度                      | `市区町村` / `都道府県` / `観測所` / `GISポイント`   |
| `update_frequency`       | 更新頻度                            | `annual` / `monthly` / `5-yearly` / `irregular`      |
| `type`                   | 値の型                              | `integer` / `ratio` / `float` / `currency` / `index` |
| `estimated_missing_rate` | 推定欠損率（`low`/`medium`/`high`） | `medium`                                             |
| `notes`                  | 備考・近似手法・要検証              | `医療圏->市区町村按分(要検証)`                       |

## 3. カタログ（指標別解説）

### 3.1 人口・世帯（基盤）

- `population`, `population_age_structure`, `single_household_ratio`, `foreign_resident_ratio`
- 出典: e-Stat（国勢調査 / 住民基本台帳）。**市区町村粒度で欠損少**。city-score の分母・重み計算の基盤。

### 3.2 キャリア持続性 / 雇用

- `job_offer_ratio`（有効求人倍率, 都道府県）, `wage_by_age`（賃金構造, 都道府県）, `industry_employment_diversity`（経済センサス, 市区町村）
- **課題**: 有効求人倍率・賃金は市区町村粒度が存在せず、都道府県値の継承 or 按分が必要 → 欠損率 medium、近似誤差あり（**要検証**）。

### 3.3 老後就労

- `elderly_employment_rate`（国勢調査）, `care_facility_capacity`, `medical_facility_density`
- 高齢者就業率は市区町村粒度あり。介護・医療は粗粒度で按分要。

### 3.4 人生コスト効率

- `housing_cost`（不動産取引価格）, `land_price`（地価公示）, `consumer_price_regional`（小売物価）
- **課題**: 取引価格は地方部で取引数が少なく欠損率 high。物価は市区町村を網羅せず（欠損率 high、**要検証**）。

### 3.5 気候ストレス

- `climate_temp_normal`, `climate_precipitation`, `climate_sunshine`（気象庁, 観測所）, `disaster_risk_flood`（国土数値情報, GIS）
- **課題**: 観測所 → 市区町村マッピング、GIS 前処理が必要（**要検証**）。

### 3.6 社会的孤立

- `single_household_ratio`, `transit_access`, `community_activity`
- 単身世帯比率は市区町村粒度あり。地域活動参加率は都道府県粒度のみ（欠損率 high、**要検証**）。

### 3.7 移住者受容度

- `net_migration_rate`（転入超過率）, `foreign_resident_ratio`
- いずれも市区町村粒度・欠損少。ただし「受容度」の直接指標ではなく**代理変数**である点に注意（解釈要注意 → 指標定義書参照）。

### 3.8 国際比較レイヤー

- `global_bli_topics`（OECD BLI）。国／地域粒度。国内スコアとは別軸。

## 4. 欠損への基本対応

1. 粒度不整合 → 上位粒度から按分/継承（手法を notes に明記）。
2. 秘匿・非公表値 → NULL 扱い、指標計算時は近傍/上位平均で補完 or 当該指標を欠測フラグ化。
3. 補完した値は**信頼度メタ**を持たせ、スコアの信頼区間表示に反映（Phase2 以降・**要検証**）。

## 5. CSV との同期ルール

- 指標の追加/削除/属性変更は **CSV を先に更新** → 本ファイルの該当節を追記。
- CI 等で「本ファイルに列挙された indicator 集合 == CSV の indicator 集合」を将来チェックする（**要検証 / 未実装**）。

## 6. 要検証項目

- [ ] 各 `estimated_missing_rate` の実測化。**要検証**。
- [ ] 都道府県 → 市区町村 按分手法の確定。**要検証**。
- [ ] 観測所・GIS → 市区町村 マッピング手法の確定。**要検証**。
- [ ] CSV/本ファイル同期チェックの自動化。**未実装**。
