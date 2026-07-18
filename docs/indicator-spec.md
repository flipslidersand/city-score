# 指標の理論的定義 (#307) + 個人体験データ取り込み仕様 (#308)

city-score の 6 指標の理論定義・計算式案・データソース・重みづけ機構を定める。加えて、客観統計を補完する**個人体験（主観）データ**の取り込み仕様を規定する。

> 計算式は「案」であり、係数・正規化方法は実データ検証で調整する（**要検証**）。最終統合版は [`indicator-spec-v2.md`](./indicator-spec-v2.md)（Phase2 指標定義書, #309）。

## 0. 設計原則

- **コスト軸に還元しない独自指標**（既存の「住みやすさランキング」との差別化）。
- すべての指標は市区町村 × 年で算出し、最終的に **0–100 に正規化**。
- ライフステージ・職種によって重みが変わる（後述の重みづけ機構）。
- 代理変数を使う指標は「代理である」ことを明示し、解釈上の限界を記す。

## 1. 正規化の共通規約

各生指標 `x` を偏差正規化（min-max, 全国市区町村分布）:

```
norm(x) = 100 * (x - p05) / (p95 - p05)   # p05,p95 = 全国5/95パーセンタイル
norm(x) = clip(norm(x), 0, 100)
```

- 外れ値の影響を抑えるため min/max ではなく p05/p95 を使用。
- 「小さいほど良い」指標（例: 災害リスク）は `100 - norm(x)` で反転。
- 欠損は当該サブ指標を重みから除外し、残りで再正規化（欠測ロバスト平均）。

## 2. 6 指標の定義

各指標は複数サブ指標の重み付き平均。以下は**サブ指標構成と方向（+/−）**。

### 2.1 キャリア持続性 (career_sustainability)

「その土地で長期にわたり働き続け、職を変えても再就職できる余地があるか」。

| サブ指標                                                   | ソース               | 方向 |
| ---------------------------------------------------------- | -------------------- | ---- |
| 有効求人倍率 `job_offer_ratio`                             | 厚労省(都道府県継承) | +    |
| 産業多様性 `industry_employment_diversity`（シャノン指数） | 経済センサス         | +    |
| 年齢別賃金の伸び `wage_by_age`                             | 賃金構造統計         | +    |
| 生産年齢人口比率                                           | 国勢調査             | +    |

```
career_sustainability = weighted_mean(
  norm(job_offer_ratio),
  norm(industry_diversity),
  norm(wage_growth),
  norm(working_age_ratio)
)
```

- 産業多様性 = シャノン指数 `H = -Σ p_i * ln(p_i)`（p_i = 産業 i の就業者シェア）。単一産業依存地域を低評価。
- **限界**: 求人倍率が都道府県粒度（代理）。**要検証**。

### 2.2 老後就労 (elderly_work_opportunity)

「高齢期にも働ける／働く場があるか」。

| サブ指標                                       | ソース       | 方向 |
| ---------------------------------------------- | ------------ | ---- |
| 65 歳以上就業率 `elderly_employment_rate`      | 国勢調査     | +    |
| 高齢者向け雇用の厚み（第三次産業・農林比率等） | 経済センサス | +    |
| 医療・介護アクセス `medical_facility_density`  | 医療施設調査 | +    |

```
elderly_work_opportunity = weighted_mean(
  norm(elderly_employment_rate),
  norm(elderly_friendly_industry_ratio),
  norm(medical_access)
)
```

- **限界**: 就業率は「働ける」と「働かざるを得ない」を区別しない → 賃金・年金と併読すべき。**要検証**。

### 2.3 人生コスト効率 (life_cost_efficiency)

「支出に対して得られる生活の質（コスパ）」。単純な安さではなく所得対比。

| サブ指標                           | ソース                | 方向                  |
| ---------------------------------- | --------------------- | --------------------- |
| 住居費 `housing_cost` / 所得       | 不動産取引価格 ÷ 賃金 | −（費用が重いほど悪） |
| 地価 `land_price`                  | 地価公示              | −                     |
| 地域物価 `consumer_price_regional` | 小売物価              | −                     |
| 所得水準 `wage_by_age`             | 賃金構造統計          | +                     |

```
life_cost_efficiency = weighted_mean(
  100 - norm(housing_cost_to_income),
  100 - norm(land_price),
  100 - norm(regional_cpi),
  norm(income_level)
)
```

- 中核は **住居費/所得比**（可処分の余裕）。
- **限界**: 物価が市区町村を網羅せず県値近似。**要検証**。

### 2.4 社会的孤立リスク (social_isolation_risk)

値が高いほど**孤立しにくい**（= 良い）方向に統一（リスクだが正規化で反転）。

| サブ指標                                        | ソース           | 方向（孤立しにくさ） |
| ----------------------------------------------- | ---------------- | -------------------- |
| 単身世帯比率 `single_household_ratio`           | 国勢調査         | −                    |
| 交通アクセス `transit_access`（駅・バス停密度） | 国土数値情報     | +                    |
| 地域活動参加率 `community_activity`             | 社会生活基本調査 | +                    |
| 医療アクセス `medical_facility_density`         | 医療施設調査     | +                    |

```
social_connectedness = weighted_mean(
  100 - norm(single_household_ratio),
  norm(transit_access),
  norm(community_activity),
  norm(medical_access)
)
```

- 出力名は「孤立しにくさ（connectedness）」として 0–100。UI で「孤立リスク = 100 − connectedness」と表示可。
- **限界**: 単身世帯 ≠ 孤立（若年単身は選好の場合も）。代理性が強い。**要検証**。

### 2.5 気候ストレス (climate_stress)

値が高いほど**ストレスが小さい**（快適）方向に統一。

| サブ指標                                | ソース       | 方向（快適さ）      |
| --------------------------------------- | ------------ | ------------------- |
| 気温の過酷さ（猛暑日/真冬日等の平年値） | 気象庁平年値 | −                   |
| 降水・積雪 `climate_precipitation`      | 気象庁       | −（過多はストレス） |
| 日照 `climate_sunshine`                 | 気象庁       | +                   |
| 災害リスク `disaster_risk_flood` 等     | 国土数値情報 | −                   |

```
climate_comfort = weighted_mean(
  100 - norm(temp_severity),
  100 - norm(precip_snow),
  norm(sunshine),
  100 - norm(disaster_risk)
)
```

- 「過酷さ」は快適域からの逸脱で定義（例: 快適気温帯からの年間逸脱度）。**要検証**（快適域の定義）。
- **限界**: 観測所 → 市区町村マッピング誤差。**要検証**。

### 2.6 移住者受容度 (migrant_openness)

「よそ者が入りやすく、定着しやすいか」。直接統計がないため代理変数中心。

| サブ指標                                 | ソース           | 方向              |
| ---------------------------------------- | ---------------- | ----------------- |
| 転入超過率 `net_migration_rate`          | 住民基本台帳移動 | +                 |
| 外国人比率 `foreign_resident_ratio`      | 住民基本台帳     | +（多様性の代理） |
| 人口の若返り（社会増による年齢構成変化） | 国勢調査/移動    | +                 |

```
migrant_openness = weighted_mean(
  norm(net_migration_rate),
  norm(foreign_resident_ratio),
  norm(population_rejuvenation)
)
```

- **限界（重要）**: いずれも「受容度」の**間接代理**。外国人比率は就労需要や工業立地の結果でもあり、寛容さと同一視できない。定義書ではこの限界を明記し、将来は主観データ（#308）で補正する。**要検証**。

## 3. 重みづけ機構

### 3.1 二段構え

最終スコア =

```
final_score(area, profile) = Σ_k  W_k(profile) * indicator_k(area)
```

- `indicator_k`: 上記 6 指標（0–100）。
- `W_k(profile)`: プロファイル（ライフステージ × 職種）依存の重み。Σ W_k = 1。

### 3.2 ライフステージ別重み（初期案）

| ステージ   | career | elderly_work | cost_eff | connect | climate | openness |
| ---------- | ------ | ------------ | -------- | ------- | ------- | -------- |
| 学生/新卒  | 0.30   | 0.00         | 0.25     | 0.20    | 0.10    | 0.15     |
| 子育て世帯 | 0.20   | 0.05         | 0.25     | 0.25    | 0.15    | 0.10     |
| 独身現役   | 0.30   | 0.05         | 0.20     | 0.20    | 0.15    | 0.10     |
| 定年前後   | 0.05   | 0.35         | 0.25     | 0.20    | 0.15    | 0.00     |
| リタイア後 | 0.00   | 0.20         | 0.25     | 0.30    | 0.25    | 0.00     |

（数値は初期案。Σ=1。**要検証**）

### 3.3 職種別補正

職種は主に `career_sustainability` の**中身**（どの産業多様性を重視するか）と全体重みを微調整する乗数として作用。

```
W_k(profile) = normalize( base_weight[stage][k] * occupation_multiplier[occupation][k] )
```

- 例: リモート可能職 → `career` の地理依存を下げ `climate`/`cost_eff` を上げる。
- 乗数テーブルは `config/weights.sample.yaml` 参照。

## 4. 個人体験データ取り込み仕様 (#308)

客観統計だけでは「実際に住んでみた肌感」を捉えられない。ユーザーの**主観スコア（体験データ）**を取り込み、客観スコアへブレンドする。

### 4.1 入力形式

- **Likert 5 段階**（1=非常に悪い 〜 5=非常に良い）を基本。任意で自由記述メモ。
- 6 指標それぞれに主観スコアを付与可能（未回答可）。
- 対象は「居住/訪問経験のある市区町村」に限定（体験の裏付け）。

### 4.2 主観 → 0–100 変換

```
subj_norm = (likert - 1) / 4 * 100   # 1→0, 3→50, 5→100
```

### 4.3 客観との合成

指標ごとに信頼度重み `alpha`（0–1）で線形ブレンド:

```
blended_k = (1 - alpha_k) * objective_k + alpha_k * subjective_k
```

- `alpha_k` は「主観をどれだけ信じるか」。既定 0.2。体験の濃さ（居住年数）や回答者数で調整可。
- 回答が無い指標は `alpha_k = 0`（客観のみ）。
- 複数ユーザー回答がある場合は主観スコアを（居住年数重み付き）平均してから合成。

### 4.4 サンプルスキーマ（YAML）

```yaml
# personal-experience.sample.yaml
version: 1
respondent: anon-user-01 # 匿名 ID。個人特定情報は保存しない
profile:
  life_stage: single_active # 3.2 のステージ ID
  occupation: software_engineer
experiences:
  - area_code: "13113" # 渋谷区 (JIS)
    area_name: 渋谷区
    residence_years: 3
    ratings: # Likert 1-5、未回答は省略
      career_sustainability: 5
      life_cost_efficiency: 2
      social_connectedness: 4
      climate_comfort: 3
      migrant_openness: 4
      # elderly_work_opportunity: 未回答 → alpha=0
    note: 仕事の選択肢は多いが家賃が重い
  - area_code: "01202" # 函館市
    area_name: 函館市
    residence_years: 1
    ratings:
      climate_comfort: 2
      life_cost_efficiency: 4
      social_connectedness: 3
    note: 冬の寒さと雪がストレス
```

### 4.4 プライバシー

- 個人特定情報（実名・住所詳細・連絡先）は保存しない。`respondent` は匿名 ID。
- 体験データは任意提供。公開スコアに含める場合は集計値のみ。**要検証**（同意フロー）。

## 5. 要検証項目

- [ ] 各サブ指標の重み初期値・正規化パーセンタイル（p05/p95）の妥当性。**要検証**。
- [ ] 代理変数（移住者受容度・社会的孤立）の妥当性検証。**要検証**。
- [ ] 快適気温帯の定義（気候ストレス）。**要検証**。
- [ ] 主観ブレンド係数 `alpha` の既定値・調整則。**要検証**。
- [ ] 欠測ロバスト平均の挙動（サブ指標が大半欠損の場合の下限件数）。**要検証**。
