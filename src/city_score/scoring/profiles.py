"""重みづけ設定・プロファイルシステム (#317)。

`config/weights.sample.yaml` を読み込み、ライフステージ×職種の組み合わせから
実効重み W_k(profile) を算出する。

    W_k(profile) = normalize( base_weights[life_stage][k] * occupation_multipliers[occupation][k] )

算出した重みは Σ=1 に再正規化する。
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG = (
    Path(__file__).resolve().parents[3] / "config" / "weights.sample.yaml"
)


class WeightsConfig:
    """重み設定のラッパ。"""

    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.indicators: list[str] = list(data["indicators"])
        self.base_weights: dict[str, dict[str, float]] = data["base_weights"]
        self.occupation_multipliers: dict[str, dict[str, float]] = data[
            "occupation_multipliers"
        ]
        self.normalization: dict[str, Any] = data.get("normalization", {})
        self.subjective_blend: dict[str, Any] = data.get("subjective_blend", {})

        self._validate()

    def _validate(self) -> None:
        """設定の整合性を検証する。

        * ``base_weights`` の各ライフステージが ``indicators`` と完全一致しない場合は
          :exc:`ValueError` を送出する（書き漏れ/誤字をフェイルファストで検知）。
        * ``occupation_multipliers`` の各職種に ``indicators`` に含まれないキーが
          存在する場合は :exc:`warnings.warn` で通知する。
        """
        indicator_set = set(self.indicators)

        for stage, weights in self.base_weights.items():
            weight_keys = set(weights.keys())
            missing = indicator_set - weight_keys
            extra = weight_keys - indicator_set
            if missing or extra:
                parts: list[str] = []
                if missing:
                    parts.append(f"missing={sorted(missing)}")
                if extra:
                    parts.append(f"extra={sorted(extra)}")
                raise ValueError(
                    f"base_weights[{stage!r}] does not match indicators — "
                    + ", ".join(parts)
                )

        for occupation, mult in self.occupation_multipliers.items():
            unknown = set(mult.keys()) - indicator_set
            if unknown:
                warnings.warn(
                    f"occupation_multipliers[{occupation!r}] contains keys not in "
                    f"indicators: {sorted(unknown)}",
                    stacklevel=2,
                )

    @property
    def life_stages(self) -> list[str]:
        return list(self.base_weights.keys())

    @property
    def occupations(self) -> list[str]:
        return list(self.occupation_multipliers.keys())

    def effective_weights(
        self, life_stage: str, occupation: str = "default"
    ) -> dict[str, float]:
        """ライフステージ×職種の実効重み（Σ=1）を返す。"""
        if life_stage not in self.base_weights:
            raise KeyError(f"unknown life_stage: {life_stage}")
        base = self.base_weights[life_stage]
        mult = self.occupation_multipliers.get(
            occupation, self.occupation_multipliers.get("default", {})
        )

        raw = {
            k: float(base.get(k, 0.0)) * float(mult.get(k, 1.0))
            for k in self.indicators
        }
        total = sum(raw.values())
        if total <= 0:
            # すべて 0 の異常時は均等配分
            n = len(self.indicators)
            return {k: 1.0 / n for k in self.indicators}
        return {k: v / total for k, v in raw.items()}


def load_weights_config(path: str | Path | None = None) -> WeightsConfig:
    """YAML から重み設定を読み込む。``path`` 省略時は同梱サンプルを使う。"""
    p = Path(path) if path else DEFAULT_CONFIG
    with open(p, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return WeightsConfig(data)
