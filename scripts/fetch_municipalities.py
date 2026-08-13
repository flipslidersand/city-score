#!/usr/bin/env python3
"""全国市区町村マスタ取得スクリプト（#320）。

e-Stat 国勢調査から市区町村コード・名前・都道府県・人口を取得し、
国土地理院の座標データと結合して CSV 出力する。

使用方法:
    python scripts/fetch_municipalities.py --api-key $ESTAT_API_KEY [--output data/municipalities_full.csv]

出力形式:
    code, name, prefecture, population, latitude, longitude (全国 1,741 件）
"""

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

# 開発時は src/ ディレクトリを PYTHONPATH に追加
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from city_score.collectors.estat_collector import EstatCollector
from city_score.data.municipalities import load_municipalities


def fetch_municipalities(api_key: str) -> pd.DataFrame:
    """e-Stat から全国市区町村マスタを取得する。

    Returns:
        code, name, prefecture, population を持つ DataFrame（全国 ~1,741 件）
    """
    # TODO C-2: 実装
    # 1. EstatCollector で国勢調査「市区町村別人口」テーブルを fetch
    # 2. load_municipalities() で既存マスタと結合
    # 3. 座標データ（国土地理院）を左結合
    # 4. 出力 DataFrame を返す

    # スタブ: 現在のサンプル CSV を返す（実装は次段階）
    return load_municipalities()


def main():
    parser = argparse.ArgumentParser(description="全国市区町村マスタ取得")
    parser.add_argument("--api-key", help="e-Stat API キー（未指定時は環境変数から取得）")
    parser.add_argument(
        "--output",
        default="data/municipalities_full.csv",
        help="出力 CSV パス（デフォルト: data/municipalities_full.csv）",
    )
    parser.add_argument("--dry-run", action="store_true", help="実行しない（確認のみ）")

    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("ESTAT_API_KEY", "")
    if not api_key:
        print("ERROR: e-Stat API キーが設定されていません")
        print("  --api-key で指定するか、環境変数 ESTAT_API_KEY を設定してください")
        sys.exit(1)

    print(f"Fetching municipalities from e-Stat API...")
    df = fetch_municipalities(api_key)

    if args.dry_run:
        print(f"[DRY-RUN] {len(df)} municipalities would be fetched")
        print(df.head())
        return

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False, encoding="utf-8")
    print(f"✓ Saved {len(df)} municipalities to {args.output}")


if __name__ == "__main__":
    main()
