"""総合スコアリングエンジン (#318)。

正規化済み指標フレームとプロファイル重みから、地域ごとの総合スコア（0〜100）を
算出しランキングを生成する。個人体験（主観スコア）のブレンドにも対応する。
"""

from __future__ import annotations

from typing import Mapping

import pandas as pd

from .normalizer import normalize_frame
from .profiles import WeightsConfig, load_weights_config


class ScoringEngine:
    """指標データ + 重み設定からスコアを計算する。

    Args:
        config: 重み設定。省略時は同梱サンプルを読み込む。
        key_cols: 指標以外の識別列（結果に保持する）。
    """

    def __init__(
        self,
        config: WeightsConfig | None = None,
        *,
        key_cols: tuple[str, ...] = ("code", "name", "prefecture"),
    ):
        self.config = config or load_weights_config()
        self.key_cols = key_cols

    # ------------------------------------------------------------------
    def score(
        self,
        indicators: pd.DataFrame,
        *,
        life_stage: str,
        occupation: str = "default",
        already_normalized: bool = False,
        subjective: Mapping[str, float] | None = None,
        alpha: float | None = None,
    ) -> pd.DataFrame:
        """地域ごとの総合スコアを算出して降順ランキングで返す。

        Args:
            indicators: ``code`` などの識別列 + 6 指標列を持つ DataFrame。
            life_stage: ライフステージ（``config.life_stages``）。
            occupation: 職種（``config.occupations``、既定 ``default``）。
            already_normalized: True なら正規化をスキップ（値は 0〜100 前提）。
            subjective: ``{code: 主観スコア(0-100)}``。指定した地域のみブレンド。
            alpha: 主観ブレンド係数。省略時は設定の ``default_alpha``。

        Returns:
            識別列 + ``score`` + ``rank`` を持つ DataFrame（score 降順）。
        """
        inds = list(self.config.indicators)
        missing = [c for c in inds if c not in indicators.columns]
        if missing:
            raise KeyError(f"missing indicator columns: {missing}")

        if already_normalized:
            norm = indicators.copy()
        else:
            n = self.config.normalization
            norm = normalize_frame(
                indicators,
                inds,
                method=n.get("method", "percentile_minmax"),
                low_percentile=n.get("low_percentile", 5),
                high_percentile=n.get("high_percentile", 95),
                clip=n.get("clip", (0, 100)),
            )

        weights = self.config.effective_weights(life_stage, occupation)
        # 欠損指標は 0 寄与ではなく、その地域の他指標だけで加重平均されるよう扱う
        weighted = pd.Series(0.0, index=norm.index)
        weight_mass = pd.Series(0.0, index=norm.index)
        for k in inds:
            col = norm[k].astype("float64")
            present = col.notna()
            weighted = weighted.add(
                (col.fillna(0.0) * weights[k]).where(present, 0.0), fill_value=0.0
            )
            weight_mass = weight_mass.add(
                pd.Series(weights[k], index=norm.index).where(present, 0.0),
                fill_value=0.0,
            )
        score = weighted / weight_mass.replace(0.0, pd.NA)

        # 主観ブレンド
        if subjective:
            a = alpha
            if a is None:
                a = float(
                    self.config.subjective_blend.get("default_alpha", 0.2)
                )
            code_col = norm["code"] if "code" in norm.columns else None
            if code_col is not None:
                subj = code_col.map(lambda c: subjective.get(str(c)))
                blended = score.copy()
                mask = subj.notna()
                blended[mask] = (1 - a) * score[mask] + a * subj[mask].astype(
                    "float64"
                )
                score = blended

        out_cols = [c for c in self.key_cols if c in norm.columns]
        result = norm[out_cols].copy()
        result["score"] = score.round(2)
        result = result.sort_values("score", ascending=False, na_position="last")
        result["rank"] = range(1, len(result) + 1)
        return result.reset_index(drop=True)
