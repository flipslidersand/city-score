"""指標の 0〜100 点正規化ロジック (#316)。

すべての指標は「高いほど良い」に揃っている前提（`config/weights.sample.yaml`
の `indicators` 参照）。生値を全国分布に対して正規化し、0〜100 のスコアにする。

対応手法:
- ``percentile_minmax``: low/high パーセンタイル間を 0〜100 に線形写像（外れ値に頑健）
- ``minmax``: 最小〜最大を 0〜100 に線形写像
- ``zscore``: z 標準化後、``clip`` 範囲へシフト・スケール（既定 0〜100）
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd


def _clip(values: pd.Series, clip: Sequence[float] | None) -> pd.Series:
    if clip is None:
        return values
    lo, hi = clip
    return values.clip(lower=lo, upper=hi)


def normalize_series(
    series: pd.Series,
    *,
    method: str = "percentile_minmax",
    low_percentile: float = 5,
    high_percentile: float = 95,
    clip: Sequence[float] | None = (0, 100),
) -> pd.Series:
    """1 指標の生値 Series を 0〜100 に正規化する。

    NaN は保持する（欠損は下流で扱う）。値がすべて同一の場合は中央値 50 を返す。
    """
    s = series.astype("float64")
    valid = s.dropna()
    if valid.empty:
        return s

    if method == "percentile_minmax":
        lo = np.nanpercentile(valid, low_percentile)
        hi = np.nanpercentile(valid, high_percentile)
    elif method == "minmax":
        lo, hi = float(valid.min()), float(valid.max())
    elif method == "zscore":
        mean, std = float(valid.mean()), float(valid.std(ddof=0))
        if std == 0:
            return pd.Series(50.0, index=s.index).where(~s.isna())
        z = (s - mean) / std
        # z を [-2, 2] とみなして 0〜100 にマップ
        scaled = (z + 2) / 4 * 100
        return _clip(scaled, clip)
    else:
        raise ValueError(f"unknown method: {method}")

    if hi == lo:
        return pd.Series(50.0, index=s.index).where(~s.isna())

    scaled = (s - lo) / (hi - lo) * 100
    return _clip(scaled, clip)


def normalize_frame(
    frame: pd.DataFrame,
    indicators: Sequence[str],
    *,
    method: str = "percentile_minmax",
    low_percentile: float = 5,
    high_percentile: float = 95,
    clip: Sequence[float] | None = (0, 100),
) -> pd.DataFrame:
    """指定した指標列を列ごとに正規化した新しい DataFrame を返す。

    指標以外の列（``code``/``name`` 等）はそのまま残す。
    """
    out = frame.copy()
    for col in indicators:
        if col not in out.columns:
            raise KeyError(f"indicator column not found: {col}")
        out[col] = normalize_series(
            out[col],
            method=method,
            low_percentile=low_percentile,
            high_percentile=high_percentile,
            clip=clip,
        )
    return out
