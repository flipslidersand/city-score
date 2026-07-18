"""e-Stat API クライアントのスモークテスト (#311)。

実ネットワークを使わず stub モードで検証する。
"""

import pytest

from city_score.clients.estat_client import EstatApiClient


def test_init_reads_api_key():
    c = EstatApiClient(api_key="dummy-key", stub=True)
    assert c.api_key == "dummy-key"
    c.close()


def test_stub_get_stats_info():
    c = EstatApiClient(api_key="dummy-key", stub=True, cache_path=None)
    c.register_stub("getStatsList", {"GET_STATS_LIST": {"RESULT": {"STATUS": 0}}})
    resp = c.get_stats_info(search_word="人口", use_cache=False)
    assert resp["GET_STATS_LIST"]["RESULT"]["STATUS"] == 0
    c.close()


def test_stub_get_data_callable():
    c = EstatApiClient(api_key="dummy-key", stub=True, cache_path=None)
    c.register_stub(
        "getStatsData",
        lambda params: {"echo": params.get("statsDataId", "")},
    )
    resp = c.get_data(stats_data_id="0000010101", use_cache=False)
    assert resp["echo"] == "0000010101"
    c.close()
