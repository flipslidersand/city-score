"""e-Stat API クライアントのスモークテスト (#311)。

実ネットワークを使わず stub モードで検証する。
キャッシュパス・ネットワークエラー・STATUS 異常のテストを含む (#20)。
"""

from unittest.mock import MagicMock

import pytest
import requests
import responses as responses_lib

from city_score.clients.estat_client import EstatApiClient, EstatApiError


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


# ------------------------------------------------------------------
# キャッシュパス (#20)
# ------------------------------------------------------------------

def test_cache_init_creates_db(tmp_path):
    """tmp_path を渡すと SQLite DB が作成されること。"""
    db_path = tmp_path / "estat_cache.db"
    c = EstatApiClient(api_key="dummy-key", stub=True, cache_path=db_path)
    assert db_path.exists()
    c.close()


def test_cache_miss_then_hit(tmp_path):
    """1 回目はスタブを呼び、2 回目はキャッシュから返すこと。"""
    db_path = tmp_path / "estat_cache.db"
    stub_payload = {"GET_STATS_LIST": {"RESULT": {"STATUS": 0}, "DATA": "v1"}}

    call_count = 0

    def counting_stub(params):
        nonlocal call_count
        call_count += 1
        return stub_payload

    c = EstatApiClient(api_key="dummy-key", stub=True, cache_path=db_path)
    c.register_stub("getStatsList", counting_stub)

    # 1 回目: ネットワーク（stub）を呼ぶ
    resp1 = c.get_stats_info(search_word="人口", use_cache=True)
    assert call_count == 1
    assert resp1["GET_STATS_LIST"]["DATA"] == "v1"

    # 2 回目: キャッシュヒットでスタブを呼ばない
    resp2 = c.get_stats_info(search_word="人口", use_cache=True)
    assert call_count == 1  # スタブは追加で呼ばれていない
    assert resp2["GET_STATS_LIST"]["DATA"] == "v1"

    c.close()


def test_cache_disabled_always_calls_stub(tmp_path):
    """use_cache=False のとき毎回スタブが呼ばれること。"""
    stub_payload = {"GET_STATS_LIST": {"RESULT": {"STATUS": 0}}}
    call_count = 0

    def counting_stub(params):
        nonlocal call_count
        call_count += 1
        return stub_payload

    c = EstatApiClient(api_key="dummy-key", stub=True, cache_path=None)
    c.register_stub("getStatsList", counting_stub)

    c.get_stats_info(search_word="人口", use_cache=False)
    c.get_stats_info(search_word="人口", use_cache=False)
    assert call_count == 2

    c.close()


# ------------------------------------------------------------------
# ネットワークエラー (#20)
# ------------------------------------------------------------------

@responses_lib.activate
def test_network_request_exception_raises_estat_api_error():
    """requests.RequestException が EstatApiError に変換されること。"""
    import responses as rsps

    rsps.add(
        rsps.GET,
        "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsList",
        body=requests.ConnectionError("connection refused"),
    )

    c = EstatApiClient(api_key="dummy-key", stub=False, cache_path=None)
    with pytest.raises(EstatApiError, match="e-Stat リクエスト失敗"):
        c.get_stats_info(search_word="人口", use_cache=False)
    c.close()


@responses_lib.activate
def test_network_http_500_raises_estat_api_error():
    """HTTP 500 が EstatApiError に変換されること。"""
    import responses as rsps

    rsps.add(
        rsps.GET,
        "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsList",
        status=500,
        body="Internal Server Error",
    )

    c = EstatApiClient(api_key="dummy-key", stub=False, cache_path=None)
    with pytest.raises(EstatApiError, match="e-Stat HTTP 500"):
        c.get_stats_info(search_word="人口", use_cache=False)
    c.close()


@responses_lib.activate
def test_network_non_json_response_raises_estat_api_error():
    """非 JSON 応答が EstatApiError に変換されること。"""
    import responses as rsps

    rsps.add(
        rsps.GET,
        "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsList",
        status=200,
        body="not-json",
        content_type="text/plain",
    )

    c = EstatApiClient(api_key="dummy-key", stub=False, cache_path=None)
    with pytest.raises(EstatApiError, match="JSON ではありません"):
        c.get_stats_info(search_word="人口", use_cache=False)
    c.close()


# ------------------------------------------------------------------
# STATUS 異常 (#20)
# ------------------------------------------------------------------

def test_check_app_status_nonzero_raises():
    """_check_app_status が STATUS!=0 のとき EstatApiError を raise すること。"""
    c = EstatApiClient(api_key="dummy-key", stub=True)
    data = {
        "GET_STATS_LIST": {
            "RESULT": {"STATUS": 1, "ERROR_MSG": "不正なパラメータです"}
        }
    }
    with pytest.raises(EstatApiError, match="STATUS=1"):
        c._check_app_status("getStatsList", data)
    c.close()


def test_check_app_status_string_nonzero_raises():
    """STATUS が文字列 '1' の場合も EstatApiError を raise すること。"""
    c = EstatApiClient(api_key="dummy-key", stub=True)
    data = {
        "GET_STATS_DATA": {
            "RESULT": {"STATUS": "1", "ERROR_MSG": "エラー"}
        }
    }
    with pytest.raises(EstatApiError, match="STATUS=1"):
        c._check_app_status("getStatsData", data)
    c.close()


def test_check_app_status_zero_ok():
    """STATUS==0 のとき例外を raise しないこと。"""
    c = EstatApiClient(api_key="dummy-key", stub=True)
    data = {"GET_STATS_LIST": {"RESULT": {"STATUS": 0}}}
    c._check_app_status("getStatsList", data)  # no exception
    c.close()


def test_stub_status_nonzero_raises_via_request():
    """stub モードで STATUS!=0 の応答が EstatApiError になること（_request 経由）。"""
    c = EstatApiClient(api_key="dummy-key", stub=True)
    c.register_stub(
        "getStatsList",
        {"GET_STATS_LIST": {"RESULT": {"STATUS": 100, "ERROR_MSG": "API 上限超過"}}},
    )
    with pytest.raises(EstatApiError, match="STATUS=100"):
        c.get_stats_info(search_word="人口", use_cache=False)
    c.close()
