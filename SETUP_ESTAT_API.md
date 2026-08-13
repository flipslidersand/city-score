# e-Stat API キー取得手順

## 概要

city-score は e-Stat（政府統計の総合窓口）から全国1,741市区町村の統計データを取得します。

## API キー取得ステップ

### 1. e-Stat ウェブサイトにアクセス
```
https://www.e-stat.go.jp/api/
```

### 2. アプリケーション ID を申請
- 「アプリケーション ID の取得」をクリック
- 名前・メールアドレスを入力
- 利用規約に同意
- **認証は不要**（無料）

### 3. アプリケーション ID を取得
- メール確認（自動）
- ID が表示される（32文字の英数字）

### 4. 環境変数に設定
```bash
export ESTAT_API_KEY="your_32char_id"
```

## 使用方法

```bash
# ドライラン（確認のみ）
python scripts/fetch_indicators.py --api-key $ESTAT_API_KEY --dry-run --year 2020

# 実データ取得
python scripts/fetch_indicators.py --api-key $ESTAT_API_KEY --year 2020 --output data/indicators_2020.csv
```

## 出力

```
data/indicators_2020.csv
├─ code: 市区町村コード（5桁）
├─ year: 年度
├─ career_sustainability: キャリア持続性
├─ elderly_work_opportunity: 老後就労機会
├─ life_cost_efficiency: 生活コスト効率
├─ social_connectedness: 社会的つながり
├─ climate_comfort: 気候快適性
└─ migrant_openness: 移住者受容度
```

## トラブル対応

### API キーが無効
- キーが正しく設定されているか確認
- キーの先頭・末尾に空白がないか確認

### データが取得できない
- ネットワーク接続を確認
- キャッシュをクリア: `rm ~/.cache/city_score/estat_cache.db`

### 実行時間が長い
- 初回は全データ取得のため 10-15 分要
- 2回目以降はキャッシュから取得（1分以内）
