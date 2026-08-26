# Streamlit Cloud デプロイ手順

city-score を [Streamlit Community Cloud](https://streamlit.io/cloud) にデプロイする手順です。

## 前提条件

- GitHub アカウント（リポジトリへの push 権限）
- [Streamlit Community Cloud](https://share.streamlit.io/) アカウント（GitHub アカウントで登録可）
- e-Stat API キー（任意。データ取得に使用。[e-Stat](https://www.e-stat.go.jp/api/) から取得）

## デプロイ手順

### 1. Streamlit Cloud にサインイン

1. https://share.streamlit.io/ を開く
2. "Continue with GitHub" でサインイン
3. リポジトリへのアクセスを許可する

### 2. 新規アプリを作成

1. "New app" をクリック
2. 以下を設定する:
   - **Repository**: `flipslidersand/city-score`
   - **Branch**: `main`
   - **Main file path**: `app.py`
3. "Advanced settings..." を開き、Python バージョンに **3.12** を指定する

### 3. Secrets の設定

`.streamlit/secrets.toml` はセキュリティ上 `.gitignore` に登録されており、リポジトリに含まれません。
Streamlit Cloud の UI から直接設定します。

1. "Advanced settings..." → "Secrets" タブを開く
2. 以下の内容を貼り付けて値を設定する:

```toml
ESTAT_API_KEY = "your-estat-api-key-here"

# 任意: キャッシュ TTL（日数、デフォルト 7）
ESTAT_CACHE_TTL_DAYS = 7
```

> テンプレートは `.streamlit/secrets.toml.example` を参照してください。

### 4. デプロイ

"Deploy!" をクリックするとビルドが開始します。
初回ビルドは 2〜5 分程度かかります。

### 5. 動作確認

デプロイ完了後、割り当てられた URL（例: `https://city-score-xxxx.streamlit.app`）にアクセスして動作を確認します。

## エントリポイント

| ファイル | 役割 |
|---|---|
| `app.py` | Streamlit Cloud 用エントリポイント（ルートに配置） |
| `src/ui/streamlit_app.py` | UI 実装本体 |

Streamlit Cloud はリポジトリルートの `app.py` を自動検出します。
`app.py` は `src/ui/streamlit_app.py` の `main()` を呼び出すシンプルなラッパーです。

## ローカル起動

```bash
# 依存関係インストール
pip install -r requirements.txt

# secrets.toml を設定（初回のみ）
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# .streamlit/secrets.toml を編集して API キーを設定

# 起動
streamlit run app.py
```

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| `ModuleNotFoundError: city_score` | `src/` が Python パスに含まれていない。`app.py` 経由で起動しているか確認 |
| データが表示されない | `src/city_score/data/sample_indicators.synthetic.csv` が存在するか確認 |
| API エラー | Streamlit Cloud の Secrets に `ESTAT_API_KEY` が設定されているか確認 |
| ビルド失敗 | `requirements.txt` のバージョン制約と Python 3.12 の互換性を確認 |
