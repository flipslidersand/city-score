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
        subjective: Mapping[str, Mapping[str, float]] | None = None,
        alpha: float | Mapping[str, float] | None = None,
    ) -> pd.DataFrame:
        """地域ごとの総合スコアを算出して降順ランキングで返す。

        Args:
            indicators: ``code`` などの識別列 + 6 指標列を持つ DataFrame。
            life_stage: ライフステージ（``config.life_stages``）。
            occupation: 職種（``config.occupations``、既定 ``default``）。
            already_normalized: True なら正規化をスキップ（値は 0〜100 前提）。
            subjective: ``{indicator_k: {code: 主観スコア(0-100)}}``。指標ごと・地域ごとにブレンド。
            alpha: 主観ブレンド係数。float なら全指標共通、Mapping なら指標ごと。省略時は設定の ``default_alpha``。
                   値域は [0.0, 1.0]。設定の ``max_alpha`` を超える値はクランプされる。

        Returns:
            識別列 + ``score`` + ``rank`` を持つ DataFrame（score 降順）。
            全指標が欠損（weight_mass=0）の行は score=NaN・rank=NaN になる。

        Raises:
            ValueError: alpha が [0.0, 1.0] の範囲外のとき。
            KeyError: 必須指標列が不足しているとき。
        """
        # --- alpha validation (fix #16) --------------------------------
        if alpha is not None:
            max_alpha = float(
                self.config.subjective_blend.get("max_alpha", 1.0)
            )
            if isinstance(alpha, dict):
                bad = {k: v for k, v in alpha.items() if not (0.0 <= float(v) <= 1.0)}
                if bad:
                    raise ValueError(
                        f"alpha values must be in [0.0, 1.0], got: {bad}"
                    )
                alpha = {k: min(float(v), max_alpha) for k, v in alpha.items()}
            else:
                alpha = float(alpha)
                if not (0.0 <= alpha <= 1.0):
                    raise ValueError(
                        f"alpha must be in [0.0, 1.0], got: {alpha}"
                    )
                alpha = min(alpha, max_alpha)

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

        # 指標単位での主観ブレンド（正規化後、加重平均前）
        blended_norm = norm.copy()
        if subjective:
            default_alpha = float(
                self.config.subjective_blend.get("default_alpha", 0.2)
            )
            code_col = blended_norm["code"].astype(str) if "code" in blended_norm.columns else None

            for k in inds:
                if k not in subjective:
                    continue
                if code_col is None:
                    continue

                # この指標の alpha を取得
                if isinstance(alpha, dict):
                    alpha_k = alpha.get(k, default_alpha)
                else:
                    alpha_k = alpha if alpha is not None else default_alpha

                # subjective[k] = {code: subj_value}
                subj_map = subjective[k]
                obj = blended_norm[k].astype("float64")

                for code, subj_val in subj_map.items():
                    mask = code_col == str(code)
                    if mask.any():
                        blended_norm.loc[mask, k] = (1 - alpha_k) * obj[mask] + alpha_k * subj_val

        # 欠損指標は 0 寄与ではなく、その地域の他指標だけで加重平均されるよう扱う
        weighted = pd.Series(0.0, index=blended_norm.index)
        weight_mass = pd.Series(0.0, index=blended_norm.index)
        for k in inds:
            col = blended_norm[k].astype("float64")
            present = col.notna()
            weighted = weighted.add(
                (col.fillna(0.0) * weights[k]).where(present, 0.0), fill_value=0.0
            )
            weight_mass = weight_mass.add(
                pd.Series(weights[k], index=blended_norm.index).where(present, 0.0),
                fill_value=0.0,
            )
        score = weighted / weight_mass.replace(0.0, pd.NA)

        out_cols = [c for c in self.key_cols if c in norm.columns]
        result = norm[out_cols].copy()
        result["score"] = score.astype("Float64").round(2)
        result = result.sort_values("score", ascending=False, na_position="last")
        # fix #16: weight_mass=0（全指標欠損）の行は rank を NaN にする
        valid_count = int(result["score"].notna().sum())
        nan_count = len(result) - valid_count
        result["rank"] = pd.array(
            [float(i) for i in range(1, valid_count + 1)]
            + [float("nan")] * nan_count,
            dtype="Float64",
        )
        return result.reset_index(drop=True)
