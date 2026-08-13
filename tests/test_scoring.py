"""スコアリングコアのテスト (#316/#317/#318)。"""

import pandas as pd
import pytest

from city_score.scoring.normalizer import normalize_series, normalize_frame
from city_score.scoring.profiles import load_weights_config
from city_score.scoring.engine import ScoringEngine

INDICATORS = [
    "career_sustainability",
    "elderly_work_opportunity",
    "life_cost_efficiency",
    "social_connectedness",
    "climate_comfort",
    "migrant_openness",
]


# --- #316 normalizer ---------------------------------------------------
def test_normalize_series_minmax_range():
    s = pd.Series([0, 5, 10])
    out = normalize_series(s, method="minmax")
    assert out.min() == 0
    assert out.max() == 100


def test_normalize_series_constant_returns_mid():
    s = pd.Series([7, 7, 7])
    out = normalize_series(s, method="minmax")
    assert (out == 50).all()


def test_normalize_series_preserves_nan():
    s = pd.Series([1.0, None, 3.0])
    out = normalize_series(s, method="minmax")
    assert out.isna().sum() == 1


def test_normalize_frame_keeps_key_cols():
    df = pd.DataFrame({"code": ["a", "b"], "career_sustainability": [1, 2]})
    out = normalize_frame(df, ["career_sustainability"])
    assert "code" in out.columns
    assert list(out["code"]) == ["a", "b"]


# --- #317 profiles -----------------------------------------------------
def test_effective_weights_sum_to_one():
    cfg = load_weights_config()
    w = cfg.effective_weights("student_newgrad", "software_engineer")
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert set(w) == set(cfg.indicators)


def test_unknown_life_stage_raises():
    cfg = load_weights_config()
    with pytest.raises(KeyError):
        cfg.effective_weights("nonexistent")


def test_occupation_multiplier_shifts_weight():
    cfg = load_weights_config()
    base = cfg.effective_weights("single_active", "default")
    swe = cfg.effective_weights("single_active", "software_engineer")
    # SWE は climate_comfort を上げる乗数なので重みが増える
    assert swe["climate_comfort"] > base["climate_comfort"]


# --- #318 engine -------------------------------------------------------
def _sample_frame():
    return pd.DataFrame(
        {
            "code": ["01100", "13101", "47201"],
            "name": ["A", "B", "C"],
            "prefecture": ["X", "Y", "Z"],
            **{k: [10, 50, 90] for k in INDICATORS},
        }
    )


def test_engine_ranks_descending():
    eng = ScoringEngine()
    res = eng.score(_sample_frame(), life_stage="single_active")
    assert list(res["rank"]) == [1, 2, 3]
    assert res["score"].iloc[0] >= res["score"].iloc[-1]
    # 全指標が単調なら C(90) が1位
    assert res.iloc[0]["name"] == "C"


def test_engine_subjective_blend_moves_score():
    eng = ScoringEngine()
    base = eng.score(_sample_frame(), life_stage="single_active")
    # 指標単位の subjective: {indicator_k: {code: subjective_value}}
    blended = eng.score(
        _sample_frame(),
        life_stage="single_active",
        subjective={
            "career_sustainability": {"01100": 100.0},  # 01100 のキャリア持続性を100に上げる
        },
        alpha=0.5,
    )
    a_base = base[base["code"] == "01100"]["score"].iloc[0]
    a_blend = blended[blended["code"] == "01100"]["score"].iloc[0]
    assert a_blend > a_base


def test_engine_missing_indicator_raises():
    eng = ScoringEngine()
    bad = _sample_frame().drop(columns=["climate_comfort"])
    with pytest.raises(KeyError):
        eng.score(bad, life_stage="single_active")
