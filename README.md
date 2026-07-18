# city-score

居住地スコアリングエンジン — キャリア持続性・人生コスト効率・老後就労等の独自指標で日本全国の住みやすさを評価する。

## 特徴

- **6 独自指標**: キャリア持続性 / 老後就労機会 / 生活コスト効率 / 社会的つながり / 気候快適性 / 移住者受容度
- **プロファイル対応**: ライフステージ × 職種で重みを変えてランキングが変わる
- **主観スコアブレンド**: 個人体験（α 係数）を客観指標に上乗せ可能
- **Streamlit UI**: 3ページ構成（ランキング / 個別スコア / プロファイル提案）

## セットアップ

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"      # コア + 開発ツール
pip install -e ".[ui]"       # Streamlit + Plotly（UI を使う場合）
```

## CLI

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

## Streamlit UI

```bash
source .venv/bin/activate
streamlit run src/ui/streamlit_app.py
# → http://localhost:8501
```

3ページ:

1. **ランキング** — 上位 N 都市テーブル + 上位3都市レーダー比較
2. **個別スコア** — 1都市の指標内訳レーダー
3. **プロファイル提案** — ライフステージ/職種/主観スコアから最適居住地を提案

## テスト

```bash
pytest          # 22 tests
pytest --cov=city_score --cov-report=term-missing
```

## 指標データ形式

`src/city_score/data/sample_indicators.synthetic.csv` （合成サンプル）の列構成:

```csv
code,career_sustainability,elderly_work_opportunity,life_cost_efficiency,
     social_connectedness,climate_comfort,migrant_openness
```

`code` は 5 桁の市区町村コード（e-Stat 標準）。実データは e-Stat API で取得後に同形式の CSV を生成してください。

## 重み設定

`config/weights.sample.yaml` を参照。ライフステージ別ベース重みと職種別乗数を YAML で定義し `--config` で指定可能。

## ディレクトリ構成

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
tests/          # 22 tests (unit + CLI integration)
```

## 注意

現在のデータは**合成サンプル**（デモ用）です。実指標値は e-Stat API 経由の取得が必要です。
