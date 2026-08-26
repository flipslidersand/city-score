"""Tests for #17: per1000/per10k transform and EstatCollector close leak."""

from __future__ import annotations

import gc

import pandas as pd
import pytest

from city_score.collectors.estat_collector import EstatCollector, StatTable


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_collector(tmp_path=None):
    """Return a stub EstatCollector with no tables (minimal overhead)."""
    return EstatCollector(stub=True, tables=[], cache_path=tmp_path)


def _make_table(transform: str) -> StatTable:
    return StatTable(
        stats_data_id="0000000001",
        description="test",
        value_key_hint="test",
        indicator_col="test_col",
        transform=transform,
    )


# ---------------------------------------------------------------------------
# per1000 / per10k transform (#17-1)
# ---------------------------------------------------------------------------

class TestPerTransform:
    """_apply_transform の per1000/per10k 分岐テスト。"""

    def setup_method(self):
        self.col = _make_collector()

    def teardown_method(self):
        self.col.close()

    def test_per1000_without_population_raises(self):
        """population 列なしで per1000 を呼ぶと NotImplementedError。"""
        df = pd.DataFrame({"code": ["01100"], "year": [2020], "_raw": [500.0]})
        table = _make_table("per1000")
        with pytest.raises(NotImplementedError, match="per1000"):
            self.col._apply_transform(df, table)

    def test_per10k_without_population_raises(self):
        """population 列なしで per10k を呼ぶと NotImplementedError。"""
        df = pd.DataFrame({"code": ["01100"], "year": [2020], "_raw": [200.0]})
        table = _make_table("per10k")
        with pytest.raises(NotImplementedError, match="per10k"):
            self.col._apply_transform(df, table)

    def test_per1000_with_population_computes_correctly(self):
        """population 列ありで per1000: raw / (pop / 1000)。"""
        df = pd.DataFrame(
            {
                "code": ["01100", "01200"],
                "year": [2020, 2020],
                "_raw": [500.0, 300.0],
                "population": [10_000.0, 5_000.0],
            }
        )
        table = _make_table("per1000")
        result = self.col._apply_transform(df.copy(), table)
        # 500 / (10000/1000) = 500/10 = 50
        assert result.loc[0, "_raw"] == pytest.approx(50.0)
        # 300 / (5000/1000) = 300/5 = 60
        assert result.loc[1, "_raw"] == pytest.approx(60.0)

    def test_per10k_with_population_computes_correctly(self):
        """population 列ありで per10k: raw / (pop / 10000)。"""
        df = pd.DataFrame(
            {
                "code": ["01100"],
                "year": [2020],
                "_raw": [100.0],
                "population": [200_000.0],
            }
        )
        table = _make_table("per10k")
        result = self.col._apply_transform(df.copy(), table)
        # 100 / (200000/10000) = 100/20 = 5
        assert result.loc[0, "_raw"] == pytest.approx(5.0)

    def test_per1000_zero_population_keeps_raw_nan_safe(self):
        """population == 0 の行は _raw をそのまま（ゼロ除算なし）。"""
        df = pd.DataFrame(
            {
                "code": ["01100", "01200"],
                "year": [2020, 2020],
                "_raw": [100.0, 200.0],
                "population": [0.0, 1_000.0],
            }
        )
        table = _make_table("per1000")
        result = self.col._apply_transform(df.copy(), table)
        # population==0 → unchanged (100.0)
        assert result.loc[0, "_raw"] == pytest.approx(100.0)
        # population==1000 → 200/(1000/1000) = 200
        assert result.loc[1, "_raw"] == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# EstatCollector close / finalizer (#17-2)
# ---------------------------------------------------------------------------

class TestEstatCollectorClose:
    """close() および weakref.finalize によるリークガードのテスト。"""

    def test_close_via_context_manager(self, tmp_path):
        """with 文で使うと __exit__ → close() が呼ばれる。"""
        with EstatCollector(stub=True, tables=[], cache_path=tmp_path / "c.db") as c:
            # finalizer は alive
            assert c._finalizer.alive
        # __exit__ 後は detach 済み → alive == False
        assert not c._finalizer.alive

    def test_explicit_close_deactivates_finalizer(self, tmp_path):
        """明示 close() で finalizer が detach されること。"""
        c = EstatCollector(stub=True, tables=[], cache_path=tmp_path / "c.db")
        assert c._finalizer.alive
        c.close()
        assert not c._finalizer.alive

    def test_double_close_does_not_raise(self, tmp_path):
        """close() を2回呼んでも例外が起きないこと。"""
        c = EstatCollector(stub=True, tables=[], cache_path=tmp_path / "c.db")
        c.close()
        c.close()  # should not raise

    def test_finalizer_closes_without_explicit_close(self, tmp_path):
        """明示 close() なしで GC されても finalizer が close() を呼ぶこと。

        EstatApiClient._cache_conn は close 後 None になるため、
        二重クローズを踏まない形で検証する。
        """
        db_path = tmp_path / "gc.db"
        c = EstatCollector(stub=True, tables=[], cache_path=db_path)
        client_ref = c._client  # hold reference to inner client
        # do NOT call c.close() — let GC trigger finalizer
        del c
        gc.collect()
        # After GC, finalizer should have called client.close(), setting _cache_conn=None
        assert client_ref._cache_conn is None
