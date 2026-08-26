"""データパイプライン統合テスト (#313/#314/#315)."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from city_score.collectors.weather_collector import JmaClient, WeatherCollector, STATION_MASTER
from city_score.collectors.estat_collector import EstatCollector, STAT_TABLES, StatTable
from city_score.processors.normalize import (
    NormalizePipeline,
    composite_indicators,
    compute_missing_stats,
    save_sqlite,
)


# ──── #313 WeatherCollector ────────────────────────────────────────────

def _stub_weather_df() -> pd.DataFrame:
    return pd.DataFrame({
        "year": [2020, 2021],
        "mean_temp": [12.5, 13.0],
        "hot_days": [5.0, 7.0],
        "heavy_snow_days": [20.0, 18.0],
        "sunshine_hours": [1800.0, 1850.0],
    })


def test_weather_collector_stub_returns_data(tmp_path):
    client = JmaClient(stub=True)
    prec, block, code = STATION_MASTER[0][:3]
    client.register_stub(prec, block, _stub_weather_df())

    collector = WeatherCollector(
        client=client,
        cache_path=None,
        stations=[STATION_MASTER[0]],
    )
    df = collector.fetch(years=[2020, 2021])
    assert not df.empty
    assert "mean_temp" in df.columns
    assert set(df["year"]) == {2020, 2021}
    assert df["code"].iloc[0] == code


def test_weather_collector_missing_station_skipped(tmp_path):
    client = JmaClient(stub=True)
    # stub 未登録 → 空 DataFrame → skip
    collector = WeatherCollector(
        client=client, cache_path=None, stations=[STATION_MASTER[0]]
    )
    df = collector.fetch(years=[2020])
    assert df.empty or len(df) == 0


def test_weather_collector_cache(tmp_path):
    client = JmaClient(stub=True)
    prec, block, code = STATION_MASTER[0][:3]
    client.register_stub(prec, block, _stub_weather_df())

    cache = tmp_path / "weather.db"
    collector = WeatherCollector(client=client, cache_path=cache, stations=[STATION_MASTER[0]])
    df1 = collector.fetch(years=[2020, 2021])
    assert cache.exists()
    # 2回目はキャッシュから取得
    df2 = collector.fetch(years=[2020, 2021])
    assert len(df1) == len(df2)


# ──── #314 EstatCollector ──────────────────────────────────────────────

def _stub_estat_response(values: list[dict]) -> dict:
    return {
        "GET_STATS_DATA": {
            "STATISTICAL_DATA": {
                "DATA_INF": {
                    "VALUE": values
                }
            }
        }
    }


def test_estat_collector_stub_fetch_table():
    stub_values = [
        {"@area": "01100", "@time": "2020CY00", "$": "45.2"},
        {"@area": "13101", "@time": "2020CY00", "$": "38.7"},
    ]
    # elderly_employment_rate を検索
    table = next(t for t in STAT_TABLES if t.indicator_col == "elderly_employment_rate")
    collector = EstatCollector(stub=True, tables=[table], cache_path=None)
    # EstatApiClient のスタブはエンドポイント名 "getStatsData" で登録する
    collector.register_stub("getStatsData", _stub_estat_response(stub_values))

    df = collector.fetch_table(table, year=2020)
    assert not df.empty
    assert "elderly_employment_rate" in df.columns
    assert set(df["code"]) == {"01100", "13101"}


def test_estat_collector_missing_key_raises():
    import os
    env_backup = os.environ.pop("ESTAT_API_KEY", None)
    try:
        with pytest.raises(ValueError, match="API key"):
            EstatCollector(stub=False, cache_path=None)
    finally:
        if env_backup:
            os.environ["ESTAT_API_KEY"] = env_backup


def test_estat_collector_shannon_transform():
    table = StatTable(
        stats_data_id="dummy",
        description="test",
        value_key_hint="産業",
        indicator_col="industry_employment_raw",
        transform="shannon",
    )
    stub_values = [
        {"@area": "13101", "@time": "2020CY00", "$": "100"},
        {"@area": "13101", "@time": "2020CY00", "$": "200"},
        {"@area": "13101", "@time": "2020CY00", "$": "300"},
    ]
    collector = EstatCollector(stub=True, tables=[table], cache_path=None)
    collector.register_stub("getStatsData", _stub_estat_response(stub_values))
    df = collector.fetch_table(table)
    assert not df.empty
    # シャノン指数は非負
    assert df["industry_employment_raw"].iloc[0] >= 0


# ──── #315 NormalizePipeline ───────────────────────────────────────────

def _sample_estat() -> pd.DataFrame:
    return pd.DataFrame({
        "code": ["01100", "13101", "47201"],
        "year": [2020, 2020, 2020],
        "elderly_employment_rate": [25.3, 18.7, 28.1],
        "industry_employment_raw": [2.1, 2.8, 1.9],
        "net_migration_raw": [500.0, 12000.0, -200.0],
        "foreign_resident_raw": [0.5, 3.2, 0.8],
    })


def _sample_weather() -> pd.DataFrame:
    return pd.DataFrame({
        "code": ["01100", "13101", "47201"],
        "year": [2020, 2020, 2020],
        "mean_temp": [8.9, 15.4, 23.1],
        "hot_days": [0.0, 10.0, 45.0],
        "heavy_snow_days": [60.0, 0.0, 0.0],
        "sunshine_hours": [1700.0, 1900.0, 2100.0],
    })


def test_pipeline_run_basic():
    pipeline = NormalizePipeline()
    df, missing = pipeline.run(
        estat_df=_sample_estat(), weather_df=_sample_weather()
    )
    assert set(df.columns) >= {"code", "year", "climate_comfort"}
    assert len(df) == 3
    assert missing.total_rows == 3


def test_pipeline_climate_comfort_range():
    pipeline = NormalizePipeline()
    df, _ = pipeline.run(estat_df=_sample_estat(), weather_df=_sample_weather())
    cc = df["climate_comfort"].dropna()
    assert (cc >= 0).all() and (cc <= 100).all()


def test_pipeline_output_sqlite(tmp_path):
    pipeline = NormalizePipeline()
    db = tmp_path / "out.db"
    df, _ = pipeline.run(
        estat_df=_sample_estat(),
        weather_df=_sample_weather(),
        output_sqlite=db,
    )
    assert db.exists()
    import sqlite3
    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT count(*) FROM indicators").fetchone()[0]
    conn.close()
    assert rows == 3


def test_pipeline_missing_stats_recorded():
    # life_cost_efficiency は housing_cost_raw がないので NaN になる
    pipeline = NormalizePipeline()
    _, missing = pipeline.run(
        estat_df=_sample_estat(), weather_df=_sample_weather()
    )
    assert "life_cost_efficiency" in missing.per_column
    assert missing.per_column["life_cost_efficiency"] == 1.0  # 全欠損


def test_pipeline_empty_inputs():
    pipeline = NormalizePipeline()
    df, missing = pipeline.run()
    assert df.empty


# ──── #9 life_cost_efficiency ゼロ除算・inf 伝播回帰テスト ──────────────

def test_life_cost_efficiency_negative_housing_cost_no_error():
    """housing_cost_raw が負値でも ZeroDivisionError / inf が発生しないこと (#9)."""
    import numpy as np
    from city_score.processors.normalize import composite_indicators

    merged = pd.DataFrame({
        "code": ["01100", "13101", "47201"],
        "year": [2020, 2020, 2020],
        "housing_cost_raw": [-1.0, -0.5, 0.0],  # 除数が 0 以下になるケース
    })
    out = composite_indicators(merged)
    lce = out["life_cost_efficiency"]

    # inf / -inf は NaN に変換されていること
    assert not np.any(np.isinf(lce.dropna())), "inf が残っている"
    # 正常値は非 NaN であること（housing_cost_raw=0.0 → denom=1.0 → 1.0/1.0=1.0）
    assert not lce.isna().all(), "全て NaN になっている"


def test_life_cost_efficiency_positive_housing_cost():
    """housing_cost_raw が正値のとき life_cost_efficiency が正しい逆数になること (#9)."""
    from city_score.processors.normalize import composite_indicators

    merged = pd.DataFrame({
        "code": ["13101"],
        "year": [2020],
        "housing_cost_raw": [4.0],  # denom=5.0 → 1/5=0.2
    })
    out = composite_indicators(merged)
    assert abs(out["life_cost_efficiency"].iloc[0] - 0.2) < 1e-9
