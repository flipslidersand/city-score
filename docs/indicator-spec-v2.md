# Phase 2 指標定義書 (最終版, #309)

Phase 1 の調査（#303–#306）と指標の理論定義（#307）・個人体験取り込み（#308）を統合した、city-score の**確定版指標定義書**。実装（スコアリングエンジン）はこの文書と `config/weights.sample.yaml` を仕様とする。

関連: [`indicator-spec.md`](./indicator-spec.md)（理論定義の詳細） / [`data-catalog.md`](./data-catalog.md)（データ台帳） / [`research/`](./research/)（ソース調査）。

## 1. スコアリング・パイプライン（確定）

```
raw data (各ソース)
  → 粒度正規化 (市区町村×年へ按分/継承/空間結合)   # data-catalog.md
  → サブ指標算出
  → 正規化 norm(x) 0-100 (p05/p95)                  # indicator-spec.md §1
  → 6 指標に集約 (欠測ロバスト重み付き平均)          # indicator-spec.md §2
  → [任意] 個人体験ブレンド (alpha)                  # indicator-spec.md §4
  → プロファイル重み適用 W_k(profile)               # weights.sample.yaml
  → final_score(area, profile) 0-100
```

## 2. 6 指標（確定サマリ, すべて「高いほど良い」）

| ID                         | 指標                   | 中核サブ指標                     | 主データソース         | 代理リスク           |
| -------------------------- | ---------------------- | -------------------------------- | ---------------------- | -------------------- |
| `career_sustainability`    | キャリア持続性         | 求人倍率, 産業多様性, 賃金の伸び | 厚労省, 経済センサス   | 中(求人倍率が県粒度) |
| `elderly_work_opportunity` | 老後就労               | 高齢就業率, 医療介護アクセス     | 国勢調査, 医療施設調査 | 中(就業率の解釈)     |
| `life_cost_efficiency`     | 人生コスト効率         | 住居費/所得比, 地価, 所得        | MLIT, 賃金構造         | 中(物価は県近似)     |
| `social_connectedness`     | 社会的孤立(の少なさ)   | 単身世帯比率(逆), 交通/地域活動  | 国勢調査, 国土数値情報 | 高(代理変数)         |
| `climate_comfort`          | 気候ストレス(の少なさ) | 気温過酷さ(逆), 日照, 災害(逆)   | 気象庁, 国土数値情報   | 中(観測所マッピング) |
| `migrant_openness`         | 移住者受容度           | 転入超過率, 外国人比率           | 住民基本台帳           | 高(間接代理)         |

## 3. 重み設定

- 機械可読サンプル: [`config/weights.sample.yaml`](../config/weights.sample.yaml)。
- 実行時は `life_stage` と `occupation` からプロファイル重みを合成:

```
W_k(profile) = normalize_sum1( base_weights[life_stage][k] * occupation_multipliers[occupation][k] )
```

## 4. 計算例（1 件, 独身現役 × ソフトウェアエンジニア）

対象: 架空市 A（説明用のダミー値。実データではない → **要検証**）。

### 4.1 正規化済み指標値（0–100, 仮）

| 指標                     | objective_k |
| ------------------------ | ----------- |
| career_sustainability    | 80          |
| elderly_work_opportunity | 40          |
| life_cost_efficiency     | 30          |
| social_connectedness     | 60          |
| climate_comfort          | 70          |
| migrant_openness         | 50          |

### 4.2 個人体験ブレンド（alpha=0.2, 一部回答あり）

回答: `life_cost_efficiency=2(→25)`, `climate_comfort=3(→50)`。他は未回答（alpha=0）。

```
blended(life_cost_efficiency) = (1-0.2)*30 + 0.2*25 = 24 + 5 = 29
blended(climate_comfort)      = (1-0.2)*70 + 0.2*50 = 56 + 10 = 66
```

| 指標                     | blended_k |
| ------------------------ | --------- |
| career_sustainability    | 80        |
| elderly_work_opportunity | 40        |
| life_cost_efficiency     | 29        |
| social_connectedness     | 60        |
| climate_comfort          | 66        |
| migrant_openness         | 50        |

### 4.3 プロファイル重み合成

base = `single_active`、multiplier = `software_engineer`（未指定指標は 1.0）:

| k                        | base | mult | base\*mult |
| ------------------------ | ---- | ---- | ---------- |
| career_sustainability    | 0.30 | 0.7  | 0.210      |
| elderly_work_opportunity | 0.05 | 1.0  | 0.050      |
| life_cost_efficiency     | 0.20 | 1.2  | 0.240      |
| social_connectedness     | 0.20 | 1.0  | 0.200      |
| climate_comfort          | 0.15 | 1.3  | 0.195      |
| migrant_openness         | 0.10 | 1.0  | 0.100      |

合計 = 0.210+0.050+0.240+0.200+0.195+0.100 = **0.995**
正規化（÷0.995）:

| k                        | W_k    |
| ------------------------ | ------ |
| career_sustainability    | 0.2111 |
| elderly_work_opportunity | 0.0503 |
| life_cost_efficiency     | 0.2412 |
| social_connectedness     | 0.2010 |
| climate_comfort          | 0.1960 |
| migrant_openness         | 0.1005 |

### 4.4 最終スコア

```
final = Σ W_k * blended_k
      = 0.2111*80 + 0.0503*40 + 0.2412*29 + 0.2010*60 + 0.1960*66 + 0.1005*50
      = 16.89 + 2.01 + 7.00 + 12.06 + 12.94 + 5.03
      = 55.9
```

**架空市 A の最終スコア ≈ 55.9 / 100**（独身現役 × ソフトウェアエンジニア プロファイル）。

解釈: キャリアは高いが、住居費負担（コスト効率の低さ）が SE プロファイルの高いコスト重みで効き、全体を押し下げている。

## 5. データ整合性チェックリスト（成果物間）

- [x] 6 指標 ID が `indicator-spec.md` / `weights.sample.yaml` / 本書で一致。
- [x] 使用データが `data-catalog.md` / `data-sources.csv` に列挙済み。
- [x] 各ソースの取得方法が `research/*.md` に記載。
- [x] 代理変数・粒度近似は「要検証」明記。

## 6. 未確定・要検証（Phase3 以降へ）

- [ ] 重み初期値・乗数の実データ検証とチューニング。
- [ ] 正規化パーセンタイル（p05/p95）の妥当性。
- [ ] 粒度按分/マッピング手法の確定と誤差評価。
- [ ] 主観ブレンド `alpha` の運用則・同意フロー。
- [ ] 国際比較レイヤー（OECD BLI）との連携方針。
