"""fetch_all / list_municipalities / _fill_prefecture_level / zscore 正規化のテスト (#21)。

Issue #21 で指摘された未テストのコアロジックをカバーする:
1. EstatCollector.fetch_all() — 複数テーブルの outer join
2. EstatApiClient.list_municipalities() — CLASS_OBJ が dict 単体のケース含む
3. NormalizePipeline._fill_prefecture_level (fill_pref_level=True) — 補完効果
4. normalize_series(method="zscore") — 値域・std=0・未知メソッドの ValueError
"""

from __future__ import annotations

import pandas as pd
import pytest

from city_score.clients.estat_client import EstatApiClient
from city_score.collectors.estat_collector import EstatCollector, StatTable
from city_score.processors.normalize import NormalizePipeline, _fill_prefecture_level
from city_score.scoring.normalizer import normalize_series


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

def _estat_response(values: list[dict]) -> dict:
    """e-Stat getStatsData 形式のスタブ応答を生成する。"""
    return {
        "GET_STATS_DATA": {
            "STATISTICAL_DATA": {
                "DATA_INF": {
                    "VALUE": values
                }
            }
        }
    }


def _meta_response(class_objs) -> dict:
    """e-Stat getMetaInfo 形式のスタブ応答を生成する。"""
    return {
        "GET_META_INFO": {
            "METADATA_INF": {
                "CLASS_INF": {
                    "CLASS_OBJ": class_objs
                }
            }
        }
    }


# ---------------------------------------------------------------------------
# 1. EstatCollector.fetch_all() — 複数テーブル outer join
# ---------------------------------------------------------------------------

def _make_two_tables() -> tuple[StatTable, StatTable]:
    t1 = StatTable(
        stats_data_id="tbl001",
        description="テーブル1",
        value_key_hint="就業",
        indicator_col="elderly_employment_rate",
        transform="identity",
    )
    t2 = StatTable(
        stats_data_id="tbl002",
        description="テーブル2",
        value_key_hint="転入",
        indicator_col="net_migration_raw",
        transform="identity",
    )
    return t1, t2


def test_fetch_all_outer_join_preserves_all_codes():
    """2 テーブルを outer join したとき、片方にしか存在しないコードが NaN で残ること。"""
    t1, t2 = _make_two_tables()
    collector = EstatCollector(stub=True, tables=[t1, t2], cache_path=None)

    # tbl001: 01100・13101 の2市区町村
    collector.register_stub(
        "getStatsData",
        lambda params: (
            _estat_response([
                {"@area": "01100", "@time": "2020CY00", "$": "25.3"},
                {"@area": "13101", "@time": "2020CY00", "$": "18.7"},
            ])
            if params.get("statsDataId") == "tbl001"
            else _estat_response([
                # tbl002: 13101・47201（01100 は欠損）
                {"@area": "13101", "@time": "2020CY00", "$": "500"},
                {"@area": "47201", "@time": "2020CY00", "$": "-200"},
            ])
        ),
    )

    df = collector.fetch_all(year=2020)

    # 全3コードが存在する
    assert set(df["code"]) == {"01100", "13101", "47201"}

    # 01100 は tbl002 に存在しないので net_migration_raw が NaN
    row_01100 = df[df["code"] == "01100"]
    assert row_01100["net_migration_raw"].isna().all()

    # 47201 は tbl001 に存在しないので elderly_employment_rate が NaN
    row_47201 = df[df["code"] == "47201"]
    assert row_47201["elderly_employment_rate"].isna().all()

    # 13101 は両テーブルに存在するので両列に値あり
    row_13101 = df[df["code"] == "13101"]
    assert not row_13101["elderly_employment_rate"].isna().all()
    assert not row_13101["net_migration_raw"].isna().all()


def test_fetch_all_single_household_ratio_computed():
    """_single_household_count / _total_household_count から single_household_ratio が計算されること。"""
    t_single = StatTable(
        stats_data_id="tbl_single",
        description="単独世帯数",
        value_key_hint="単独",
        indicator_col="_single_household_count",
        transform="identity",
    )
    t_total = StatTable(
        stats_data_id="tbl_total",
        description="総世帯数",
        value_key_hint="世帯",
        indicator_col="_total_household_count",
        transform="identity",
    )
    collector = EstatCollector(stub=True, tables=[t_single, t_total], cache_path=None)

    collector.register_stub(
        "getStatsData",
        lambda params: (
            _estat_response([{"@area": "13101", "@time": "2020CY00", "$": "200"}])
            if params.get("statsDataId") == "tbl_single"
            else _estat_response([{"@area": "13101", "@time": "2020CY00", "$": "1000"}])
        ),
    )

    df = collector.fetch_all(year=2020)

    # 中間列は削除されていること
    assert "_single_household_count" not in df.columns
    assert "_total_household_count" not in df.columns

    # single_household_ratio = 200/1000 * 100 = 20.0
    assert "single_household_ratio" in df.columns
    assert abs(df["single_household_ratio"].iloc[0] - 20.0) < 1e-9


def test_fetch_all_empty_tables_returns_code_year():
    """テーブルが空のとき code・year 列だけの DataFrame が返ること。"""
    collector = EstatCollector(stub=True, tables=[], cache_path=None)
    df = collector.fetch_all()
    assert list(df.columns) == ["code", "year"]
    assert df.empty


# ---------------------------------------------------------------------------
# 2. EstatApiClient.list_municipalities()
# ---------------------------------------------------------------------------

def _build_class_obj(classes) -> dict:
    return {"@id": "area", "CLASS": classes}


def test_list_municipalities_returns_list_of_dicts():
    """list_municipalities が {"code", "name", "level", "parent"} の list を返すこと。"""
    classes = [
        {"@code": "01100", "@name": "札幌市", "@level": "3", "@parentCode": "01"},
        {"@code": "13101", "@name": "千代田区", "@level": "4", "@parentCode": "13"},
    ]
    client = EstatApiClient(api_key="dummy", stub=True, cache_path=None)
    client.register_stub("getMetaInfo", _meta_response([_build_class_obj(classes)]))

    result = client.list_municipalities("dummy_id", use_cache=False)

    assert len(result) == 2
    assert result[0]["code"] == "01100"
    assert result[0]["name"] == "札幌市"
    assert result[0]["level"] == "3"
    assert result[0]["parent"] == "01"
    client.close()


def test_list_municipalities_class_obj_as_dict_single():
    """CLASS_OBJ が dict 単体（1 分類のみ）のとき正常に処理されること。"""
    classes = [
        {"@code": "01100", "@name": "札幌市", "@level": "3", "@parentCode": "01"},
    ]
    # CLASS_OBJ が list ではなく dict 単体
    single_obj = _build_class_obj(classes)
    client = EstatApiClient(api_key="dummy", stub=True, cache_path=None)
    client.register_stub("getMetaInfo", _meta_response(single_obj))

    result = client.list_municipalities("dummy_id", use_cache=False)
    assert len(result) == 1
    assert result[0]["code"] == "01100"
    client.close()


def test_list_municipalities_class_as_dict_single_entry():
    """CLASS が dict 単体（1 エントリのみ）のとき list 化されて処理されること。"""
    single_class = {"@code": "01100", "@name": "札幌市", "@level": "3", "@parentCode": "01"}
    obj = {"@id": "area", "CLASS": single_class}  # CLASS が dict
    client = EstatApiClient(api_key="dummy", stub=True, cache_path=None)
    client.register_stub("getMetaInfo", _meta_response([obj]))

    result = client.list_municipalities("dummy_id", use_cache=False)
    assert len(result) == 1
    assert result[0]["code"] == "01100"
    client.close()


def test_list_municipalities_non_area_class_obj_skipped():
    """area 以外の分類 ID を持つ CLASS_OBJ はスキップされること。"""
    classes = [{"@code": "01", "@name": "北海道", "@level": "1", "@parentCode": ""}]
    non_area_obj = {"@id": "time", "CLASS": classes}
    area_obj = _build_class_obj(classes)
    client = EstatApiClient(api_key="dummy", stub=True, cache_path=None)
    client.register_stub("getMetaInfo", _meta_response([non_area_obj, area_obj]))

    # area_class_id="area" のみカウント → 1 件のみ
    result = client.list_municipalities("dummy_id", use_cache=False)
    assert len(result) == 1
    client.close()


def test_list_municipalities_empty_class_obj():
    """CLASS_OBJ が空リストのとき空リストを返すこと。"""
    client = EstatApiClient(api_key="dummy", stub=True, cache_path=None)
    client.register_stub("getMetaInfo", _meta_response([]))

    result = client.list_municipalities("dummy_id", use_cache=False)
    assert result == []
    client.close()


# ---------------------------------------------------------------------------
# 3. NormalizePipeline._fill_prefecture_level — fill_pref_level=True
# ---------------------------------------------------------------------------

def test_fill_prefecture_level_fills_missing_with_pref_mean():
    """同一都道府県内の欠損値が都道府県平均で補完されること。"""
    df = pd.DataFrame({
        "code": ["01100", "01200", "13101"],
        "year": [2020, 2020, 2020],
        "elderly_employment_rate": [25.0, float("nan"), 30.0],
    })
    result = _fill_prefecture_level(df)

    # 01200 は 01100 と同一都道府県 (01)。01 の平均は 25.0 のみ → 25.0 で補完
    val_01200 = result.loc[result["code"] == "01200", "elderly_employment_rate"].iloc[0]
    assert abs(val_01200 - 25.0) < 1e-9


def test_fill_prefecture_level_does_not_overwrite_existing():
    """元の値が存在する行は上書きされないこと。"""
    df = pd.DataFrame({
        "code": ["13101", "13102"],
        "year": [2020, 2020],
        "elderly_employment_rate": [18.0, 22.0],
    })
    result = _fill_prefecture_level(df)

    assert abs(result.loc[result["code"] == "13101", "elderly_employment_rate"].iloc[0] - 18.0) < 1e-9
    assert abs(result.loc[result["code"] == "13102", "elderly_employment_rate"].iloc[0] - 22.0) < 1e-9


def test_fill_pref_level_via_pipeline_run():
    """NormalizePipeline.run(fill_pref_level=True) が欠損を都道府県平均で補完すること。"""
    # 01100 と同一都道府県(01)に 01200 を追加し、01200 は elderly_employment_rate が欠損
    estat_df = pd.DataFrame({
        "code": ["01100", "01200"],
        "year": [2020, 2020],
        "elderly_employment_rate": [25.0, float("nan")],
    })
    pipeline = NormalizePipeline()
    out_df, _ = pipeline.run(estat_df=estat_df, fill_pref_level=True)

    val = out_df.loc[out_df["code"] == "01200", "elderly_work_opportunity"].iloc[0]
    # 01 都道府県の平均 = 25.0 で補完されているはず
    assert not pd.isna(val)
    assert abs(val - 25.0) < 1e-9


def test_fill_pref_level_false_leaves_nan():
    """NormalizePipeline.run(fill_pref_level=False) のとき欠損が補完されないこと。"""
    estat_df = pd.DataFrame({
        "code": ["01100", "01200"],
        "year": [2020, 2020],
        "elderly_employment_rate": [25.0, float("nan")],
    })
    pipeline = NormalizePipeline()
    out_df, _ = pipeline.run(estat_df=estat_df, fill_pref_level=False)

    val = out_df.loc[out_df["code"] == "01200", "elderly_work_opportunity"].iloc[0]
    assert pd.isna(val)


# ---------------------------------------------------------------------------
# 4. normalize_series(method="zscore") — 値域・std=0・未知メソッド
# ---------------------------------------------------------------------------

def test_zscore_output_within_0_100_by_default():
    """zscore 正規化した結果が clip=(0,100) 内に収まること。"""
    s = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0, 100.0, 200.0])
    out = normalize_series(s, method="zscore")
    assert (out.dropna() >= 0).all()
    assert (out.dropna() <= 100).all()


def test_zscore_std_zero_returns_50():
    """全値が同一（標準偏差=0）のとき 50 を返すこと。"""
    s = pd.Series([7.0, 7.0, 7.0])
    out = normalize_series(s, method="zscore")
    assert (out == 50.0).all()


def test_zscore_preserves_nan():
    """NaN は保持されること。"""
    s = pd.Series([1.0, float("nan"), 3.0])
    out = normalize_series(s, method="zscore")
    assert out.isna().sum() == 1


def test_zscore_spread_values_are_ordered():
    """値が大きいほど正規化後も大きくなること（単調性）。"""
    s = pd.Series([1.0, 2.0, 3.0])
    out = normalize_series(s, method="zscore")
    assert out.iloc[0] < out.iloc[1] < out.iloc[2]


def test_unknown_method_raises_value_error():
    """未知の method 文字列を指定したとき ValueError が送出されること。"""
    s = pd.Series([1.0, 2.0, 3.0])
    with pytest.raises(ValueError, match="unknown method"):
        normalize_series(s, method="invalid_method")
