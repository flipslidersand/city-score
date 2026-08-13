#!/usr/bin/env python3
"""指標一括取得スクリプト（#322）。

e-Stat + 気象庁から複数テーブルをバッチ取得し、
city-score の 6 指標に合成して CSV/Parquet で出力する。

使用方法:
    python scripts/fetch_indicators.py --api-key $ESTAT_API_KEY [--year 2020] [--output data/indicators_2020.csv]

出力形式:
    code, year, career_sustainability, elderly_work_opportunity, life_cost_efficiency,
    social_connectedness, climate_comfort, migrant_openness
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# 開発時は src/ ディレクトリを PYTHONPATH に追加
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from city_score.collectors.estat_collector import EstatCollector
from city_score.collectors.weather_collector import WeatherCollector
from city_score.processors.normalize import NormalizePipeline


def fetch_indicators(api_key: str, year: int | None = None) -> pd.DataFrame:
    """e-Stat + 気象庁から指標を一括取得。

    Args:
        api_key: e-Stat API キー
        year: 取得対象年度（未指定時は 2020）

    Returns:
        code, year + 6 指標 の DataFrame
    """
    if year is None:
        year = 2020

    print(f"  Fetching e-Stat data (year={year})...")
    with EstatCollector(api_key=api_key) as estat:
        estat_df = estat.fetch_all(year=year)
    print(f"    → {len(estat_df)} rows from e-Stat")

    print(f"  Fetching weather data (years=[{year}])...")
    with WeatherCollector() as weather:
        weather_df = weather.fetch(years=[year])
    print(f"    → {len(weather_df)} rows from JMA")

    print(f"  Composing indicators...")
    pipeline = NormalizePipeline()
    result_df, missing = pipeline.run(
        estat_df=estat_df,
        weather_df=weather_df,
        fill_pref_level=True,
    )

    print(f"  Missing stats:\n{missing.report()}")
    return result_df


def main():
    parser = argparse.ArgumentParser(description="指標一括取得")
    parser.add_argument("--api-key", help="e-Stat API キー（未指定時は環境変数から取得）")
    parser.add_argument("--year", type=int, default=2020, help="取得対象年度（デフォルト: 2020）")
    parser.add_argument(
        "--output",
        help="出力 CSV パス（未指定時: data/indicators_YYYYMMDD.csv）",
    )
    parser.add_argument("--output-parquet", help="出力 Parquet パス（オプション）")
    parser.add_argument("--dry-run", action="store_true", help="実行しない（確認のみ）")

    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("ESTAT_API_KEY", "")
    if not api_key:
        print("ERROR: e-Stat API キーが設定されていません")
        print("  --api-key で指定するか、環境変数 ESTAT_API_KEY を設定してください")
        sys.exit(1)

    output_path = args.output or f"data/indicators_{datetime.now().strftime('%Y%m%d')}.csv"

    if args.dry_run:
        print(f"[DRY-RUN] Would fetch indicators for year={args.year}")
        print(f"[DRY-RUN] Would output to: {output_path}")
        return

    print(f"Fetching indicators for year {args.year}...")
    df = fetch_indicators(api_key, year=args.year)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8")
    print(f"✓ Saved {len(df)} indicators to {output_path}")

    if args.output_parquet:
        df.to_parquet(args.output_parquet, index=False, engine="pyarrow")
        print(f"✓ Also saved to {args.output_parquet}")


if __name__ == "__main__":
    main()
