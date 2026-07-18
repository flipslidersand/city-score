"""データ正規化・一元化パイプライン (#315).

複数ソース（e-Stat / JMA気象）を市区町村コード×年度で結合し、
city-score の6指標に合成して Parquet または SQLite に出力する。

パイプライン概要:
  1. WeatherCollector → weather DataFrame (code, year, mean_temp, ...)
  2. EstatCollector  → estat DataFrame  (code, year, elderly_employment_rate, ...)
  3. join on (code, year) → merged DataFrame
  4. 指標合成 (composite_indicators) → 6指標 DataFrame
  5. 欠損統計記録 → missing_stats
  6. Parquet / SQLite 出力

出力スキーマ:
  code (str), year (int),
  career_sustainability, elderly_work_opportunity, life_cost_efficiency,
  social_connectedness, climate_comfort, migrant_openness (すべて float, 生値)
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

INDICATOR_COLS = [
    "career_sustainability",
    "elderly_work_opportunity",
    "life_cost_efficiency",
    "social_connectedness",
    "climate_comfort",
    "migrant_openness",
]


@dataclass
class MissingStats:
    """欠損率の記録。"""

    total_rows: int = 0
    per_column: dict[str, float] = field(default_factory=dict)

    def report(self) -> str:
        lines = [f"total_rows: {self.total_rows}"]
        for col, rate in sorted(self.per_column.items()):
            lines.append(f"  {col}: {rate:.1%}")
        return "\n".join(lines)


def _compute_climate_comfort(df: pd.DataFrame) -> pd.Series:
    """気象指標から climate_comfort (0〜100相当の生値) を合成する。

    高いほど快適な方向に統一（後段で全指標を一括正規化）。
    - mean_temp: 適温（15〜20℃）からの偏差を罰則化
    - hot_days: 多いほど不快（反転）
    - heavy_snow_days: 多いほど不快（反転）
    - sunshine_hours: 多いほど快適

    各成分を [0, 1] にクリップ後、単純平均。
    """
    parts = pd.DataFrame(index=df.index)

    # 平均気温: 18℃が最適、偏差が大きいほど低スコア
    if "mean_temp" in df.columns:
        dev = (df["mean_temp"] - 18.0).abs()
        parts["temp_comfort"] = (1 - (dev / 20).clip(0, 1)) * 100
    else:
        parts["temp_comfort"] = float("nan")

    # 猛暑日: 年30日を上限として線形罰則
    if "hot_days" in df.columns:
        parts["hot_penalty"] = (1 - (df["hot_days"] / 30).clip(0, 1)) * 100
    else:
        parts["hot_penalty"] = float("nan")

    # 豪雪: 年30日を上限として線形罰則
    if "heavy_snow_days" in df.columns:
        parts["snow_penalty"] = (1 - (df["heavy_snow_days"] / 30).clip(0, 1)) * 100
    else:
        parts["snow_penalty"] = float("nan")

    # 日照時間: 年2400hが最大想定
    if "sunshine_hours" in df.columns:
        parts["sunshine_score"] = (df["sunshine_hours"] / 2400).clip(0, 1) * 100
    else:
        parts["sunshine_score"] = float("nan")

    return parts.mean(axis=1, skipna=True)


def composite_indicators(merged: pd.DataFrame) -> pd.DataFrame:
    """結合済み DataFrame から6指標 DataFrame を合成する。

    Args:
        merged: (code, year) + e-Stat/気象生値列 を持つ DataFrame

    Returns:
        code, year + INDICATOR_COLS の DataFrame（生値、正規化前）
    """
    out = merged[["code", "year"]].copy()

    # career_sustainability: 産業多様性（シャノン指数）× 高齢者以外の就業率代理
    if "industry_employment_raw" in merged.columns:
        out["career_sustainability"] = merged["industry_employment_raw"]
    else:
        out["career_sustainability"] = float("nan")

    # elderly_work_opportunity: 高齢者就業率
    if "elderly_employment_rate" in merged.columns:
        out["elderly_work_opportunity"] = merged["elderly_employment_rate"]
    else:
        out["elderly_work_opportunity"] = float("nan")

    # life_cost_efficiency: housing_cost の逆数（データあれば）or 欠損
    if "housing_cost_raw" in merged.columns:
        out["life_cost_efficiency"] = 1.0 / (merged["housing_cost_raw"] + 1)
    else:
        out["life_cost_efficiency"] = float("nan")

    # social_connectedness: 単身世帯比率の逆数（高いほど孤立リスク→反転）
    if "single_household_ratio" in merged.columns:
        out["social_connectedness"] = 100 - merged["single_household_ratio"]
    else:
        out["social_connectedness"] = float("nan")

    # climate_comfort: 気象指標の合成
    out["climate_comfort"] = _compute_climate_comfort(merged)

    # migrant_openness: 転入超過率 + 外国人比率の合成
    components = []
    if "net_migration_raw" in merged.columns:
        components.append(merged["net_migration_raw"].clip(lower=0))
    if "foreign_resident_raw" in merged.columns:
        components.append(merged["foreign_resident_raw"])
    if components:
        out["migrant_openness"] = pd.concat(components, axis=1).mean(axis=1, skipna=True)
    else:
        out["migrant_openness"] = float("nan")

    return out


def compute_missing_stats(df: pd.DataFrame) -> MissingStats:
    stats = MissingStats(total_rows=len(df))
    for col in df.columns:
        if col in ("code", "year"):
            continue
        stats.per_column[col] = float(df[col].isna().mean())
    return stats


def save_parquet(df: pd.DataFrame, path: str | Path) -> None:
    """DataFrame を Parquet 形式で保存する。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p, index=False, engine="pyarrow")


def save_sqlite(df: pd.DataFrame, path: str | Path, table: str = "indicators") -> None:
    """DataFrame を SQLite テーブルとして保存する。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    df.to_sql(table, conn, if_exists="replace", index=False)
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_code_year ON {table} (code, year)")
    conn.commit()
    conn.close()


class NormalizePipeline:
    """e-Stat + 気象 データを結合・合成・出力するパイプライン。

    Usage::

        pipeline = NormalizePipeline()
        result_df, missing = pipeline.run(
            estat_df=estat_collector.fetch_all(year=2020),
            weather_df=weather_collector.fetch(years=[2020]),
            output_parquet="data/indicators_2020.parquet",
        )
        print(missing.report())
    """

    def run(
        self,
        *,
        estat_df: pd.DataFrame | None = None,
        weather_df: pd.DataFrame | None = None,
        output_parquet: str | Path | None = None,
        output_sqlite: str | Path | None = None,
        sqlite_table: str = "indicators",
        fill_pref_level: bool = True,
    ) -> tuple[pd.DataFrame, MissingStats]:
        """パイプラインを実行する。

        Args:
            estat_df:      EstatCollector.fetch_all() の出力
            weather_df:    WeatherCollector.fetch() の出力
            output_parquet: 出力 Parquet パス（省略時は保存しない）
            output_sqlite:  出力 SQLite パス（省略時は保存しない）
            fill_pref_level: True のとき都道府県レベル値で市区町村欠損を補完

        Returns:
            (indicator_df, MissingStats)
        """
        # 1. マージ
        frames = []
        if estat_df is not None and not estat_df.empty:
            frames.append(estat_df)
        if weather_df is not None and not weather_df.empty:
            frames.append(weather_df)

        if not frames:
            empty = pd.DataFrame(columns=["code", "year"] + INDICATOR_COLS)
            return empty, MissingStats()

        merged = frames[0]
        for df in frames[1:]:
            merged = merged.merge(df, on=["code", "year"], how="outer")

        merged["code"] = merged["code"].astype(str).str.zfill(5)
        merged["year"] = pd.to_numeric(merged["year"], errors="coerce").astype("Int64")
        merged = merged.dropna(subset=["code", "year"])

        # 2. 都道府県レベル補完（code[:2] が同じ行で欠損補完）
        if fill_pref_level:
            merged = _fill_prefecture_level(merged)

        # 3. 指標合成
        indicator_df = composite_indicators(merged)

        # 4. 欠損統計
        missing = compute_missing_stats(indicator_df)

        # 5. 出力
        if output_parquet:
            save_parquet(indicator_df, output_parquet)
        if output_sqlite:
            save_sqlite(indicator_df, output_sqlite, table=sqlite_table)

        return indicator_df, missing


def _fill_prefecture_level(df: pd.DataFrame) -> pd.DataFrame:
    """都道府県コード（先頭2桁）レベルの平均値で市区町村欠損を補完する。

    元の値が存在する場合は上書きしない。
    """
    numeric_cols = [c for c in df.columns if c not in ("code", "year") and
                    pd.api.types.is_numeric_dtype(df[c])]
    if not numeric_cols:
        return df

    df = df.copy()
    df["_pref"] = df["code"].str[:2]

    pref_means = (
        df.groupby(["_pref", "year"])[numeric_cols]
        .mean()
        .reset_index()
        .rename(columns={c: f"_pref_{c}" for c in numeric_cols})
    )
    df = df.merge(pref_means, on=["_pref", "year"], how="left")

    for col in numeric_cols:
        fill_col = f"_pref_{col}"
        if fill_col in df.columns:
            df[col] = df[col].fillna(df[fill_col])
            df.drop(columns=[fill_col], inplace=True)

    df.drop(columns=["_pref"], inplace=True)
    return df
