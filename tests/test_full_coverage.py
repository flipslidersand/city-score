"""Tests for Issue #7: 気象データの全都市カバレッジ拡張.

- StationIndex が全地点を読み込めることを確認
- get_station_for_municipality の動作確認
- compute_missing_rate の動作確認
- カバレッジ率 >= 95% の確認（全47都道府県に対して）
"""
from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import pytest

from city_score.collectors.weather_collector import StationIndex

# テスト用 config ディレクトリ (プロジェクトルートの config/)
_PROJECT_ROOT = Path(__file__).parent.parent
_CONFIG_DIR = _PROJECT_ROOT / "config"


class TestStationIndexLoad:
    """StationIndex が config ファイルを正しく読み込めること。"""

    def test_loads_all_stations(self):
        idx = StationIndex(config_dir=_CONFIG_DIR)
        stations = idx.stations
        # 全47都道府県をカバーする地点が存在すること
        assert len(stations) >= 47, f"Expected >= 47 stations, got {len(stations)}"

    def test_all_stations_have_required_fields(self):
        idx = StationIndex(config_dir=_CONFIG_DIR)
        required = {"station_id", "name", "prefecture", "lat", "lon"}
        for st in idx.stations:
            missing = required - set(st.keys())
            assert not missing, f"Station {st.get('name')} missing fields: {missing}"

    def test_station_coordinates_are_valid(self):
        idx = StationIndex(config_dir=_CONFIG_DIR)
        for st in idx.stations:
            assert 20 <= st["lat"] <= 46, f"Invalid lat for {st['name']}: {st['lat']}"
            assert 122 <= st["lon"] <= 154, f"Invalid lon for {st['name']}: {st['lon']}"

    def test_missing_config_dir_does_not_raise(self):
        """存在しない config ディレクトリでも例外を投げないこと。"""
        idx = StationIndex(config_dir=Path("/nonexistent/path"))
        assert idx.stations == []


class TestGetStationForMunicipality:
    """get_station_for_municipality の動作確認。"""

    def setup_method(self):
        self.idx = StationIndex(config_dir=_CONFIG_DIR)

    def test_tokyo_returns_station(self):
        st = self.idx.get_station_for_municipality("13101")
        assert st is not None
        assert st["prefecture"] == "東京都"

    def test_osaka_returns_station(self):
        st = self.idx.get_station_for_municipality("27100")
        assert st is not None
        assert st["prefecture"] == "大阪府"

    def test_hokkaido_returns_station(self):
        st = self.idx.get_station_for_municipality("01100")
        assert st is not None
        assert st["prefecture"] == "北海道"

    def test_okinawa_returns_station(self):
        st = self.idx.get_station_for_municipality("47201")
        assert st is not None
        assert st["prefecture"] == "沖縄県"

    def test_unknown_code_returns_none(self):
        st = self.idx.get_station_for_municipality("99999")
        assert st is None

    def test_six_digit_code_works(self):
        """6桁コードでも先頭2桁で都道府県を判定できること。"""
        st = self.idx.get_station_for_municipality("130001")
        assert st is not None
        assert st["prefecture"] == "東京都"

    def test_all_47_prefectures_covered(self):
        """全47都道府県の代表コードに対して地点が返ること。"""
        missing = []
        for pref_num in range(1, 48):
            code = f"{pref_num:02d}0000"
            st = self.idx.get_station_for_municipality(code)
            if st is None:
                missing.append(code)
        assert not missing, f"No station found for prefecture codes: {missing}"


class TestFindNearestStation:
    """find_nearest_station の動作確認。"""

    def setup_method(self):
        self.idx = StationIndex(config_dir=_CONFIG_DIR)

    def test_tokyo_coordinates_returns_tokyo_station(self):
        st = self.idx.find_nearest_station(35.6894, 139.6917)
        assert st is not None
        assert st["prefecture"] == "東京都"

    def test_osaka_coordinates_returns_osaka_station(self):
        st = self.idx.find_nearest_station(34.6842, 135.5192)
        assert st is not None
        assert st["prefecture"] == "大阪府"

    def test_returns_none_when_no_stations(self):
        idx = StationIndex(config_dir=Path("/nonexistent"))
        result = idx.find_nearest_station(35.0, 135.0)
        assert result is None


class TestComputeMissingRate:
    """compute_missing_rate の動作確認。"""

    def test_no_missing_data(self):
        records = [
            {"mean_temp": 15.0, "hot_days": 5.0, "heavy_snow_days": 0.0, "sunshine_hours": 2000.0},
            {"mean_temp": 16.0, "hot_days": 8.0, "heavy_snow_days": 0.0, "sunshine_hours": 2100.0},
        ]
        rate = StationIndex.compute_missing_rate(records)
        assert rate == 0.0

    def test_all_missing_data(self):
        records = [
            {"mean_temp": None, "hot_days": None, "heavy_snow_days": None, "sunshine_hours": None},
        ]
        rate = StationIndex.compute_missing_rate(records)
        assert rate == 1.0

    def test_half_missing_data(self):
        records = [
            {"mean_temp": 15.0, "hot_days": None, "heavy_snow_days": 0.0, "sunshine_hours": None},
        ]
        rate = StationIndex.compute_missing_rate(records)
        assert rate == pytest.approx(0.5)

    def test_nan_counts_as_missing(self):
        records = [
            {"mean_temp": float("nan"), "hot_days": 5.0, "heavy_snow_days": 0.0, "sunshine_hours": 2000.0},
        ]
        rate = StationIndex.compute_missing_rate(records)
        assert rate == pytest.approx(0.25)

    def test_empty_results_returns_one(self):
        rate = StationIndex.compute_missing_rate([])
        assert rate == 1.0

    def test_dataclass_like_objects(self):
        """WeatherRecord のようなデータクラスでも動作すること。"""
        from city_score.collectors.weather_collector import WeatherRecord
        records = [
            WeatherRecord(code="13101", year=2023, mean_temp=15.0, hot_days=None,
                          heavy_snow_days=0.0, sunshine_hours=2000.0),
        ]
        rate = StationIndex.compute_missing_rate([vars(r) for r in records])
        assert rate == pytest.approx(0.25)


class TestCoverageRate:
    """全都市カバレッジ率 >= 95% の確認。"""

    def test_coverage_rate_for_47_prefectures(self):
        """47都道府県の代表コードに対するカバレッジ率が100%であること。"""
        idx = StationIndex(config_dir=_CONFIG_DIR)
        codes = [f"{p:02d}0000" for p in range(1, 48)]
        rate = idx.coverage_rate(codes)
        assert rate >= 0.95, f"Coverage rate {rate:.1%} is below 95%"

    def test_coverage_rate_with_municipality_codes(self):
        """市区町村コード形式でも高いカバレッジ率を達成すること。"""
        idx = StationIndex(config_dir=_CONFIG_DIR)
        # 各都道府県から複数の市区町村コードを生成（スタブ）
        codes = []
        for p in range(1, 48):
            for city in range(1, 5):
                codes.append(f"{p:02d}{city:04d}")
        rate = idx.coverage_rate(codes)
        assert rate >= 0.95, f"Coverage rate {rate:.1%} is below 95%"

    def test_coverage_rate_empty_list(self):
        idx = StationIndex(config_dir=_CONFIG_DIR)
        rate = idx.coverage_rate([])
        assert rate == 0.0


class TestBuildStationMapScript:
    """scripts/build_station_map.py の動作確認。"""

    def test_haversine_km_basic(self):
        """ハーバーサイン距離計算の基本確認。"""
        from scripts.build_station_map import haversine_km  # type: ignore[import]
        # 東京 → 大阪 はおよそ 400km
        dist = haversine_km(35.6894, 139.6917, 34.6842, 135.5192)
        assert 380 < dist < 430, f"Tokyo-Osaka distance {dist:.1f} km out of expected range"

    def test_build_mapping_returns_valid_structure(self):
        """build_mapping がスタブデータで正しい構造を返すこと。"""
        from scripts.build_station_map import build_mapping  # type: ignore[import]
        result = build_mapping(_CONFIG_DIR / "amedas_stations.json")
        assert "version" in result
        assert "mappings" in result
        assert "coverage_rate" in result
        assert result["coverage_rate"] == 1.0
        assert result["total_municipalities"] == 47  # スタブは47都道府県
