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


# --- #15 base_weights validation (fail-fast) ---------------------------

def _make_data(base_weights_override: dict | None = None, occ_override: dict | None = None) -> dict:
    """テスト用の最小 WeightsConfig データを生成する。"""
    indicators = [
        "career_sustainability",
        "elderly_work_opportunity",
        "life_cost_efficiency",
        "social_connectedness",
        "climate_comfort",
        "migrant_openness",
    ]
    full_base = {k: 1.0 for k in indicators}
    base_weights = {"test_stage": base_weights_override if base_weights_override is not None else full_base}
    occupation_multipliers = occ_override if occ_override is not None else {
        "default": {k: 1.0 for k in indicators}
    }
    return {
        "indicators": indicators,
        "base_weights": base_weights,
        "occupation_multipliers": occupation_multipliers,
    }


def test_base_weights_missing_key_raises():
    """base_weights に指標が欠けていれば ValueError が出る。"""
    from city_score.scoring.profiles import WeightsConfig

    incomplete = {
        "career_sustainability": 0.3,
        # elderly_work_opportunity 書き漏れ
        "life_cost_efficiency": 0.2,
        "social_connectedness": 0.2,
        "climate_comfort": 0.15,
        "migrant_openness": 0.15,
    }
    with pytest.raises(ValueError, match=r"base_weights\[.test_stage.\]"):
        WeightsConfig(_make_data(base_weights_override=incomplete))


def test_base_weights_extra_key_raises():
    """base_weights に indicators 外のキーがあれば ValueError が出る。"""
    from city_score.scoring.profiles import WeightsConfig

    extra = {
        "career_sustainability": 0.2,
        "elderly_work_opportunity": 0.2,
        "life_cost_efficiency": 0.2,
        "social_connectedness": 0.1,
        "climate_comfort": 0.15,
        "migrant_openness": 0.15,
        "unknown_indicator": 0.0,  # 余分なキー
    }
    with pytest.raises(ValueError, match="extra="):
        WeightsConfig(_make_data(base_weights_override=extra))


def test_occupation_multiplier_unknown_key_warns():
    """occupation_multipliers に indicators 外のキーがあれば UserWarning が出る。"""
    from city_score.scoring.profiles import WeightsConfig

    occ = {
        "default": {
            "career_sustainability": 1.0,
            "elderly_work_opportunity": 1.0,
            "life_cost_efficiency": 1.0,
            "social_connectedness": 1.0,
            "climate_comfort": 1.0,
            "migrant_openness": 1.0,
            "nonexistent_key": 1.0,  # 誤字
        }
    }
    with pytest.warns(UserWarning, match="nonexistent_key"):
        WeightsConfig(_make_data(occ_override=occ))


def test_valid_config_loads_without_error():
    """完全一致の設定は例外・警告なしでロードできる。"""
    cfg = load_weights_config()
    assert set(cfg.indicators) == {
        "career_sustainability",
        "elderly_work_opportunity",
        "life_cost_efficiency",
        "social_connectedness",
        "climate_comfort",
        "migrant_openness",
    }


# --- #16 alpha validation & weight_mass=0 rank fix --------------------
def test_engine_alpha_out_of_range_raises():
    """alpha > 1 は ValueError を送出する（fix #16）。"""
    eng = ScoringEngine()
    with pytest.raises(ValueError, match="alpha"):
        eng.score(_sample_frame(), life_stage="single_active", alpha=1.5)


def test_engine_alpha_negative_raises():
    """alpha < 0 は ValueError を送出する（fix #16）。"""
    eng = ScoringEngine()
    with pytest.raises(ValueError, match="alpha"):
        eng.score(_sample_frame(), life_stage="single_active", alpha=-0.1)


def test_engine_alpha_clamped_to_max_alpha():
    """alpha が max_alpha（0.5）を超える場合は 0.5 にクランプされる（fix #16）。"""
    eng = ScoringEngine()
    # max_alpha=0.5 なので alpha=0.5 と同じ結果になるはず
    res_clamped = eng.score(
        _sample_frame(),
        life_stage="single_active",
        subjective={"career_sustainability": {"01100": 100.0}},
        alpha=0.5,
    )
    # alpha=0.5 で直接渡した場合と比較（クランプ後と同一の入力値なので同一結果）
    res_direct = eng.score(
        _sample_frame(),
        life_stage="single_active",
        subjective={"career_sustainability": {"01100": 100.0}},
        alpha=0.5,
    )
    pd.testing.assert_frame_equal(res_clamped, res_direct)


def test_engine_all_nan_indicators_rank_is_nan():
    """全指標が欠損の行は rank が NaN になる（fix #16）。"""
    df = _sample_frame().copy()
    # 3行目の全指標を NaN にする
    for k in INDICATORS:
        df.loc[2, k] = None
    eng = ScoringEngine()
    res = eng.score(df, life_stage="single_active", already_normalized=True)
    nan_rows = res[res["score"].isna()]
    assert len(nan_rows) == 1
    assert pd.isna(nan_rows["rank"].iloc[0])
    # NaN 以外の行は連番 1, 2 になっている
    valid_rows = res[res["score"].notna()]
    assert list(valid_rows["rank"]) == [1, 2]
