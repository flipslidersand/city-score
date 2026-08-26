"""EstatCollector ページネーションテスト (#18).

fetch_table() が TOTAL_NUMBER > TO_NUMBER のとき startPosition を進めて
全件取得することを stub モードで検証する。
"""

from __future__ import annotations

import pytest

from city_score.collectors.estat_collector import EstatCollector, StatTable


def _make_page(
    values: list[dict],
    *,
    total_number: int,
    from_number: int,
    to_number: int,
) -> dict:
    """ページ付き e-Stat 応答を組み立てる。"""
    return {
        "GET_STATS_DATA": {
            "STATISTICAL_DATA": {
                "TABLE_INF": {
                    "TOTAL_NUMBER": total_number,
                    "FROM_NUMBER": from_number,
                    "TO_NUMBER": to_number,
                },
                "DATA_INF": {
                    "VALUE": values,
                },
            }
        }
    }


def _simple_table(indicator_col: str = "test_col") -> StatTable:
    return StatTable(
        stats_data_id="dummy_id",
        description="テスト用",
        value_key_hint="テスト",
        indicator_col=indicator_col,
        transform="identity",
    )


# ------------------------------------------------------------------
# 単一ページ（ページング不要）
# ------------------------------------------------------------------

def test_fetch_table_single_page_no_pagination():
    """TOTAL_NUMBER == TO_NUMBER のとき 1 回だけ API を呼ぶこと。"""
    table = _simple_table("test_col")
    call_count = 0

    def stub(params):
        nonlocal call_count
        call_count += 1
        return _make_page(
            [
                {"@area": "01100", "@time": "2020CY00", "$": "10"},
                {"@area": "13101", "@time": "2020CY00", "$": "20"},
            ],
            total_number=2,
            from_number=1,
            to_number=2,
        )

    collector = EstatCollector(stub=True, tables=[table], cache_path=None)
    collector.register_stub("getStatsData", stub)

    df = collector.fetch_table(table)
    assert call_count == 1
    assert len(df) == 2
    assert set(df["code"]) == {"01100", "13101"}
    collector.close()


# ------------------------------------------------------------------
# 2 ページ
# ------------------------------------------------------------------

def test_fetch_table_two_pages_collects_all_rows():
    """2 ページにまたがるデータを全件取得すること。"""
    table = _simple_table("test_col")
    page1_values = [{"@area": "01100", "@time": "2020CY00", "$": "1"}]
    page2_values = [{"@area": "13101", "@time": "2020CY00", "$": "2"}]
    calls: list[dict] = []

    def stub(params):
        calls.append(dict(params))
        start = int(params.get("startPosition", 1))
        if start == 1:
            return _make_page(page1_values, total_number=2, from_number=1, to_number=1)
        else:
            return _make_page(page2_values, total_number=2, from_number=2, to_number=2)

    collector = EstatCollector(stub=True, tables=[table], cache_path=None)
    collector.register_stub("getStatsData", stub)

    df = collector.fetch_table(table)
    assert len(calls) == 2
    assert int(calls[0].get("startPosition", 1)) == 1
    assert int(calls[1]["startPosition"]) == 2
    assert len(df) == 2
    assert set(df["code"]) == {"01100", "13101"}
    collector.close()


# ------------------------------------------------------------------
# 3 ページ（ページサイズより多い件数）
# ------------------------------------------------------------------

def test_fetch_table_three_pages_collects_all_rows():
    """3 ページにまたがるデータを全件取得すること。"""
    table = _simple_table("test_col")

    def make_row(area: str) -> dict:
        return {"@area": area, "@time": "2020CY00", "$": "5"}

    pages = {
        1: ([make_row("01100")], 3, 1, 1),
        2: ([make_row("13101")], 3, 2, 2),
        3: ([make_row("27100")], 3, 3, 3),
    }
    call_starts: list[int] = []

    def stub(params):
        start = int(params.get("startPosition", 1))
        call_starts.append(start)
        vals, total, frm, to = pages[start]
        return _make_page(vals, total_number=total, from_number=frm, to_number=to)

    collector = EstatCollector(stub=True, tables=[table], cache_path=None)
    collector.register_stub("getStatsData", stub)

    df = collector.fetch_table(table)
    assert call_starts == [1, 2, 3]
    assert len(df) == 3
    assert set(df["code"]) == {"01100", "13101", "27100"}
    collector.close()


# ------------------------------------------------------------------
# TABLE_INF が欠落している応答（後方互換）
# ------------------------------------------------------------------

def test_fetch_table_missing_table_inf_returns_single_page():
    """TABLE_INF がない古い形式の応答でもデータを返すこと。"""
    table = _simple_table("test_col")
    call_count = 0

    def stub(params):
        nonlocal call_count
        call_count += 1
        # TABLE_INF なし
        return {
            "GET_STATS_DATA": {
                "STATISTICAL_DATA": {
                    "DATA_INF": {
                        "VALUE": [
                            {"@area": "01100", "@time": "2020CY00", "$": "42"}
                        ]
                    }
                }
            }
        }

    collector = EstatCollector(stub=True, tables=[table], cache_path=None)
    collector.register_stub("getStatsData", stub)

    df = collector.fetch_table(table)
    assert call_count == 1
    assert len(df) == 1
    assert df["test_col"].iloc[0] == 42.0
    collector.close()


# ------------------------------------------------------------------
# TOTAL_NUMBER == 0 のとき無限ループしない
# ------------------------------------------------------------------

def test_fetch_table_total_number_zero_no_infinite_loop():
    """TOTAL_NUMBER=0 のとき 1 回だけ呼んで終了すること。"""
    table = _simple_table("test_col")
    call_count = 0

    def stub(params):
        nonlocal call_count
        call_count += 1
        return _make_page([], total_number=0, from_number=0, to_number=0)

    collector = EstatCollector(stub=True, tables=[table], cache_path=None)
    collector.register_stub("getStatsData", stub)

    df = collector.fetch_table(table)
    assert call_count == 1
    assert df.empty
    collector.close()


# ------------------------------------------------------------------
# startPosition・limit パラメータが API に渡っていること
# ------------------------------------------------------------------

def test_fetch_table_passes_start_position_and_limit():
    """各ページのリクエストに startPosition と limit が含まれること。"""
    table = _simple_table("test_col")
    received_params: list[dict] = []

    def stub(params):
        received_params.append(dict(params))
        start = int(params.get("startPosition", 1))
        if start == 1:
            return _make_page(
                [{"@area": "01100", "@time": "2020CY00", "$": "1"}],
                total_number=2,
                from_number=1,
                to_number=1,
            )
        return _make_page(
            [{"@area": "13101", "@time": "2020CY00", "$": "2"}],
            total_number=2,
            from_number=2,
            to_number=2,
        )

    collector = EstatCollector(stub=True, tables=[table], cache_path=None)
    collector.register_stub("getStatsData", stub)

    collector.fetch_table(table)

    for p in received_params:
        assert "startPosition" in p, "startPosition がリクエストに含まれていない"
        assert "limit" in p, "limit がリクエストに含まれていない"
    collector.close()
