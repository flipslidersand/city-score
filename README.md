![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

# city-score

A residential scoring engine for Japanese cities — evaluates livability using original metrics such as career sustainability, life-cost efficiency, and elderly employment opportunity.

---

## English

### Overview

**city-score** ranks all 1,741 Japanese municipalities using six original indicators, adjusting weights dynamically based on your life stage and occupation. You can also blend in subjective personal experience scores to personalize the results.

### Features

- **6 original indicators**: Career Sustainability / Elderly Work Opportunity / Life-Cost Efficiency / Social Connectedness / Climate Comfort / Migrant Openness
- **Profile-aware ranking**: Weights shift based on life stage × occupation combinations
- **Subjective score blending**: Personal experience (α coefficient) layered on top of objective indicators
- **Streamlit UI**: 3-page app (Ranking / Individual Score / Profile Suggestions)

### Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"      # core + dev tools
pip install -e ".[ui]"       # Streamlit + Plotly (for UI)
```

### CLI Usage

```bash
# Ranking (table format)
city-score ranking --life-stage single_active --occupation software_engineer --top 10

# Ranking (Markdown format)
city-score ranking --life-stage family_raising --format markdown --top 20

# Score for a single municipality
city-score score --code 13101 --life-stage single_active

# List profiles and effective weights
city-score profiles --life-stage pre_retirement --occupation healthcare_worker
```

To use real data, pass `--indicators path/to/data.csv` (default: synthetic sample).

### Streamlit UI

```bash
source .venv/bin/activate
streamlit run src/ui/streamlit_app.py
# → http://localhost:8501
```

3 pages:

1. **Ranking** — Top-N cities table + radar chart comparison of top 3
2. **Individual Score** — Indicator breakdown radar for a single city
3. **Profile Suggestions** — Recommends best cities based on life stage / occupation / subjective scores

### Fetching Real Data

**Prerequisite:** e-Stat API key (free) → [SETUP_ESTAT_API.md](SETUP_ESTAT_API.md)

```bash
# Dry run (check only)
python scripts/fetch_indicators.py --api-key $ESTAT_API_KEY --dry-run --year 2020

# Fetch all 1,741 municipalities
python scripts/fetch_indicators.py --api-key $ESTAT_API_KEY --year 2020 --output data/indicators_2020.csv
```

Output: `data/indicators_YYYYMMDD.csv` (1,741 rows × 9 columns)

### Testing

```bash
pytest          # 33 tests
pytest --cov=city_score --cov-report=term-missing
```

### Indicator Data Format

Columns of `src/city_score/data/sample_indicators.synthetic.csv` (synthetic sample):

```csv
code,career_sustainability,elderly_work_opportunity,life_cost_efficiency,
     social_connectedness,climate_comfort,migrant_openness
```

`code` is the 5-digit municipality code (e-Stat standard). Generate a CSV in the same format from real e-Stat API data.

### Weight Configuration

See `config/weights.sample.yaml`. Define base weights per life stage and occupation multipliers in YAML; pass with `--config`.

### Directory Structure

```text
src/city_score/
  clients/      # e-Stat API client
  data/         # Municipality master + synthetic sample indicators
  scoring/      # normalizer / profiles / engine
  cli.py        # CLI entry point
src/ui/
  streamlit_app.py   # Streamlit 3-page UI
config/
  weights.sample.yaml
tests/          # 33 tests (unit + CLI integration)
```

### Note

The default dataset is **synthetic (demo only)**. Real indicator values require fetching via the e-Stat API.

---

## 日本語

### 概要

**city-score** は、6つの独自指標を使って日本全国1,741市区町村の住みやすさをスコアリングするエンジンです。ライフステージ・職種に応じて重みを動的に調整し、個人の主観スコアをブレンドすることでパーソナライズされたランキングを生成します。

### 特徴

- **6 独自指標**: キャリア持続性 / 老後就労機会 / 生活コスト効率 / 社会的つながり / 気候快適性 / 移住者受容度
- **プロファイル対応**: ライフステージ × 職種で重みが変化しランキングが変わる
- **主観スコアブレンド**: 個人体験（α 係数）を客観指標に上乗せ可能
- **Streamlit UI**: 3ページ構成（ランキング / 個別スコア / プロファイル提案）

### セットアップ

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"      # コア + 開発ツール
pip install -e ".[ui]"       # Streamlit + Plotly（UI を使う場合）
```

### CLI

```bash
# ランキング（表形式）
city-score ranking --life-stage single_active --occupation software_engineer --top 10

# ランキング（Markdown）
city-score ranking --life-stage family_raising --format markdown --top 20

# 単一市区町村スコア
city-score score --code 13101 --life-stage single_active

# プロファイル一覧・実効重み確認
city-score profiles --life-stage pre_retirement --occupation healthcare_worker
```

実データがある場合は `--indicators path/to/data.csv` で差し替え（デフォルト: 合成サンプル）。

### Streamlit UI

```bash
source .venv/bin/activate
streamlit run src/ui/streamlit_app.py
# → http://localhost:8501
```

3ページ:

1. **ランキング** — 上位 N 都市テーブル + 上位3都市レーダー比較
2. **個別スコア** — 1都市の指標内訳レーダー
3. **プロファイル提案** — ライフステージ/職種/主観スコアから最適居住地を提案

### 実データ取得

**前提条件:** e-Stat API キー（無料取得）→ [SETUP_ESTAT_API.md](SETUP_ESTAT_API.md)

```bash
# 確認（ドライラン）
python scripts/fetch_indicators.py --api-key $ESTAT_API_KEY --dry-run --year 2020

# 実行（全国1,741市区町村のデータ取得）
python scripts/fetch_indicators.py --api-key $ESTAT_API_KEY --year 2020 --output data/indicators_2020.csv
```

出力: `data/indicators_YYYYMMDD.csv`（全1,741行×9列）

### テスト

```bash
pytest          # 33 tests
pytest --cov=city_score --cov-report=term-missing
```

### 指標データ形式

`src/city_score/data/sample_indicators.synthetic.csv` （合成サンプル）の列構成:

```csv
code,career_sustainability,elderly_work_opportunity,life_cost_efficiency,
     social_connectedness,climate_comfort,migrant_openness
```

`code` は 5 桁の市区町村コード（e-Stat 標準）。実データは e-Stat API で取得後に同形式の CSV を生成してください。

### 重み設定

`config/weights.sample.yaml` を参照。ライフステージ別ベース重みと職種別乗数を YAML で定義し `--config` で指定可能。

### ディレクトリ構成

```text
src/city_score/
  clients/      # e-Stat API クライアント
  data/         # 市区町村マスタ・合成サンプル指標
  scoring/      # 正規化(normalizer) / プロファイル(profiles) / エンジン(engine)
  cli.py        # CLI エントリポイント
src/ui/
  streamlit_app.py   # Streamlit 3ページ UI
config/
  weights.sample.yaml
tests/          # 33 tests (unit + CLI integration)
```

### 注意

現在のデータは**合成サンプル**（デモ用）です。実指標値は e-Stat API 経由の取得が必要です。
