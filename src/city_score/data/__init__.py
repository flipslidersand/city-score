"""市区町村マスタ等の基盤データ。"""

from city_score.data.municipalities import (
    load_municipalities,
    normalize_municipality_name,
)

__all__ = ["load_municipalities", "normalize_municipality_name"]
