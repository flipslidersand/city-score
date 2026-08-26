"""e-Stat API v3.0 クライアント (#311).

政府統計の総合窓口 (e-Stat) の API 機能 (v3.0, JSON) を叩く薄いクライアント。
仕様は ``docs/research/estat-api.md`` に整合させている。

主な仕様（estat-api.md 参照）:
- 認証: アプリケーション ID (``appId``) 方式。各リクエストのクエリに付与。
  city-score では環境変数 ``ESTAT_API_KEY`` から読む。
- ベース URL: ``https://api.e-stat.go.jp/rest/3.0/app/json/``
- エンドポイント: ``getStatsList`` / ``getMetaInfo`` / ``getStatsData``
- レート制限: 明示的な RPS 上限は非公表（**要検証**）。過度な連続アクセスを避け、
  取得済みレスポンスは SQLite にキャッシュする。

設計方針:
- ネットワークは ``requests`` 経由。テストでは ``responses`` 等でモックする。
- ``stub`` モードでは実ネットワークを使わず、登録済みスタブ応答を返す
  （オフライン開発・CI 用）。
- レスポンスは (url, params) をキーに SQLite キャッシュ。年次バッチ想定。
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable

import requests

# estat-api.md §4: JSON 版ベース URL
BASE_URL = "https://api.e-stat.go.jp/rest/3.0/app/json/"

# 市区町村地域コードの分類 ID（getMetaInfo/getStatsData の地域軸）。
# 実表によって @id が異なる場合があるため利用側で上書き可（**要検証**）。
DEFAULT_AREA_CLASS_ID = "area"

_ENV_KEY = "ESTAT_API_KEY"


class EstatApiError(RuntimeError):
    """e-Stat API 呼び出しでのエラー（HTTP・アプリ両方）。"""


class EstatApiClient:
    """e-Stat API v3.0 (JSON) クライアント。

    Args:
        api_key: appId。省略時は環境変数 ``ESTAT_API_KEY`` から取得。
        base_url: API ベース URL。テスト時などに差し替え可能。
        cache_path: SQLite キャッシュファイルパス。``None`` でキャッシュ無効。
        session: ``requests.Session``。未指定なら内部生成。
        stub: スタブモード。有効時は実ネットワークを使わず、
            ``register_stub`` で登録した応答を返す。
        request_interval: 連続リクエスト間の最小スリープ秒（レート配慮）。
        timeout: HTTP タイムアウト秒。
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = BASE_URL,
        cache_path: str | os.PathLike[str] | None = None,
        session: requests.Session | None = None,
        stub: bool = False,
        request_interval: float = 0.0,
        timeout: float = 30.0,
        cache_ttl_days: int | None = None,
    ) -> None:
        self.stub = stub
        self.api_key = api_key if api_key is not None else os.environ.get(_ENV_KEY)
        if not self.stub and not self.api_key:
            raise EstatApiError(
                f"e-Stat appId が未設定です。引数 api_key か環境変数 {_ENV_KEY} を設定してください。"
            )
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self.request_interval = request_interval
        self._session = session or requests.Session()
        self._last_request_ts = 0.0

        # キャッシュ TTL（秒）
        if cache_ttl_days is None:
            cache_ttl_days = int(os.environ.get("ESTAT_CACHE_TTL_DAYS", "7"))
        self.cache_ttl_seconds = cache_ttl_days * 86400

        # スタブ応答レジストリ: endpoint -> callable(params) -> dict
        self._stubs: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}

        self._cache_conn: sqlite3.Connection | None = None
        if cache_path is not None:
            self._cache_conn = self._init_cache(Path(cache_path))

    # ------------------------------------------------------------------
    # キャッシュ
    # ------------------------------------------------------------------
    @staticmethod
    def _init_cache(path: Path) -> sqlite3.Connection:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS estat_cache (
                cache_key TEXT PRIMARY KEY,
                endpoint  TEXT NOT NULL,
                payload   TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        conn.commit()
        return conn

    @staticmethod
    def _cache_key(endpoint: str, params: dict[str, Any]) -> str:
        # appId はキャッシュキーから除外（同一クエリを共有できるように）。
        safe = {k: v for k, v in params.items() if k != "appId"}
        blob = endpoint + "?" + json.dumps(safe, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def _cache_get(self, key: str) -> dict[str, Any] | None:
        if self._cache_conn is None:
            return None
        row = self._cache_conn.execute(
            "SELECT payload, created_at FROM estat_cache WHERE cache_key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        payload, created_at = row
        # TTL チェック
        age = time.time() - created_at
        if age > self.cache_ttl_seconds:
            return None
        return json.loads(payload)

    def _cache_put(self, key: str, endpoint: str, payload: dict[str, Any]) -> None:
        if self._cache_conn is None:
            return
        self._cache_conn.execute(
            "INSERT OR REPLACE INTO estat_cache "
            "(cache_key, endpoint, payload, created_at) VALUES (?, ?, ?, ?)",
            (key, endpoint, json.dumps(payload, ensure_ascii=False), time.time()),
        )
        self._cache_conn.commit()

    # ------------------------------------------------------------------
    # スタブモード
    # ------------------------------------------------------------------
    def register_stub(
        self,
        endpoint: str,
        response: dict[str, Any] | Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        """スタブ応答を登録する（``stub=True`` 時に使用）。

        Args:
            endpoint: ``getStatsData`` などのエンドポイント名。
            response: 返す dict、または params を受け取り dict を返す callable。
        """
        if callable(response):
            self._stubs[endpoint] = response
        else:
            self._stubs[endpoint] = lambda _params, _r=response: _r

    # ------------------------------------------------------------------
    # 低レベル呼び出し
    # ------------------------------------------------------------------
    def _throttle(self) -> None:
        if self.request_interval <= 0:
            return
        elapsed = time.monotonic() - self._last_request_ts
        wait = self.request_interval - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request_ts = time.monotonic()

    def _request(
        self, endpoint: str, params: dict[str, Any], *, use_cache: bool
    ) -> dict[str, Any]:
        clean = {k: v for k, v in params.items() if v is not None}
        cache_key = self._cache_key(endpoint, clean)

        if use_cache:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

        if self.stub:
            data = self._request_stub(endpoint, clean)
        else:
            data = self._request_network(endpoint, clean)

        self._check_app_status(endpoint, data)

        if use_cache:
            self._cache_put(cache_key, endpoint, data)
        return data

    def _request_stub(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        handler = self._stubs.get(endpoint)
        if handler is None:
            raise EstatApiError(
                f"stub モードですが '{endpoint}' のスタブ応答が未登録です。"
                " register_stub() で登録してください。"
            )
        return handler(params)

    def _request_network(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        query = {"appId": self.api_key, **params}
        self._throttle()
        try:
            resp = self._session.get(
                self.base_url + endpoint, params=query, timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise EstatApiError(f"e-Stat リクエスト失敗 ({endpoint}): {exc}") from exc
        if resp.status_code != 200:
            raise EstatApiError(
                f"e-Stat HTTP {resp.status_code} ({endpoint}): {resp.text[:200]}"
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise EstatApiError(
                f"e-Stat 応答が JSON ではありません ({endpoint})"
            ) from exc

    @staticmethod
    def _check_app_status(endpoint: str, data: dict[str, Any]) -> None:
        """e-Stat 応答のアプリケーションレベルの STATUS を検査する。

        v3.0 は各応答のルート直下に ``RESULT`` (STATUS/ERROR_MSG) を持つ。
        STATUS が 0 以外はエラー扱い（**要検証**: STATUS コード網羅）。
        """
        # 応答ルートは "GET_STATS_DATA" などエンドポイント別。RESULT を探索。
        for value in data.values():
            if isinstance(value, dict) and "RESULT" in value:
                result = value["RESULT"]
                status = result.get("STATUS")
                if status not in (0, "0", None):
                    msg = result.get("ERROR_MSG", "unknown error")
                    raise EstatApiError(
                        f"e-Stat API エラー ({endpoint}): STATUS={status} {msg}"
                    )
                return

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------
    def get_stats_info(
        self,
        *,
        stats_data_id: str | None = None,
        search_word: str | None = None,
        stats_code: str | None = None,
        limit: int | None = None,
        use_cache: bool = True,
        **extra: Any,
    ) -> dict[str, Any]:
        """統計表情報を取得する（``getStatsList``）。

        利用可能な統計表 (``statsDataId``) を検索する。
        ``stats_data_id`` を渡すと特定表のメタ情報寄りの応答になる。

        Args:
            stats_data_id: 統計表 ID。
            search_word: 検索キーワード。
            stats_code: 政府統計コード。
            limit: 取得件数上限。
            use_cache: キャッシュ利用可否。
            **extra: 追加クエリパラメータ（``surveyYears`` 等）。

        Returns:
            e-Stat の生 JSON（dict）。
        """
        params: dict[str, Any] = {
            "statsDataId": stats_data_id,
            "searchWord": search_word,
            "statsCode": stats_code,
            "limit": limit,
            **extra,
        }
        return self._request("getStatsList", params, use_cache=use_cache)

    def get_meta_info(
        self, stats_data_id: str, *, use_cache: bool = True, **extra: Any
    ) -> dict[str, Any]:
        """統計表のメタ情報（分類定義）を取得する（``getMetaInfo``）。

        地域・時間・カテゴリのコード⇔名称対応表を取得する。
        """
        params: dict[str, Any] = {"statsDataId": stats_data_id, **extra}
        return self._request("getMetaInfo", params, use_cache=use_cache)

    def get_data(
        self,
        stats_data_id: str,
        *,
        cd_area: str | list[str] | None = None,
        cd_time: str | list[str] | None = None,
        cd_cat01: str | None = None,
        start_position: int | None = None,
        limit: int | None = None,
        meta_get_flg: str = "Y",
        cnt_get_flg: str = "N",
        use_cache: bool = True,
        **extra: Any,
    ) -> dict[str, Any]:
        """統計データ本体を取得する（``getStatsData``）。

        Args:
            stats_data_id: 統計表 ID（必須）。
            cd_area: 地域コード（5 桁 JIS）。list はカンマ区切りに変換。
            cd_time: 時間軸コード。list はカンマ区切りに変換。
            cd_cat01: 分類コード。
            start_position: ページング開始位置（1 始まり）。
            limit: 取得件数上限（最大 10 万件）。
            meta_get_flg: メタ情報同梱フラグ。
            cnt_get_flg: 件数のみ取得フラグ。
            use_cache: キャッシュ利用可否。
            **extra: 追加クエリパラメータ。

        Returns:
            e-Stat の生 JSON（dict）。値は ``GET_STATS_DATA`` 配下。
        """
        params: dict[str, Any] = {
            "statsDataId": stats_data_id,
            "cdArea": _join_codes(cd_area),
            "cdTime": _join_codes(cd_time),
            "cdCat01": cd_cat01,
            "startPosition": start_position,
            "limit": limit,
            "metaGetFlg": meta_get_flg,
            "cntGetFlg": cnt_get_flg,
            **extra,
        }
        return self._request("getStatsData", params, use_cache=use_cache)

    def list_municipalities(
        self,
        stats_data_id: str,
        *,
        area_class_id: str = DEFAULT_AREA_CLASS_ID,
        use_cache: bool = True,
    ) -> list[dict[str, str]]:
        """統計表のメタ情報から市区町村（地域）コード一覧を抽出する。

        ``getMetaInfo`` の ``CLASS_INF`` にある地域軸 (``@id == area_class_id``)
        の ``CLASS`` 要素を ``{"code", "name", "level", "parent"}`` の
        list に整形して返す。

        Args:
            stats_data_id: 統計表 ID。
            area_class_id: 地域軸の分類 ID（既定 ``"area"``、表により異なる）。
            use_cache: キャッシュ利用可否。

        Returns:
            地域コード一覧。市区町村レベル以外（都道府県・全国）も含む。
            粒度の絞り込みは呼び出し側で ``level`` を見て行う（**要検証**:
            level 値の意味は表依存）。
        """
        meta = self.get_meta_info(stats_data_id, use_cache=use_cache)
        class_objs = (
            meta.get("GET_META_INFO", {})
            .get("METADATA_INF", {})
            .get("CLASS_INF", {})
            .get("CLASS_OBJ", [])
        )
        if isinstance(class_objs, dict):
            class_objs = [class_objs]

        result: list[dict[str, str]] = []
        for obj in class_objs:
            if obj.get("@id") != area_class_id:
                continue
            classes = obj.get("CLASS", [])
            if isinstance(classes, dict):
                classes = [classes]
            for cls in classes:
                result.append(
                    {
                        "code": str(cls.get("@code", "")),
                        "name": str(cls.get("@name", "")),
                        "level": str(cls.get("@level", "")),
                        "parent": str(cls.get("@parentCode", "")),
                    }
                )
        return result

    def close(self) -> None:
        """内部リソース（キャッシュ接続・セッション）を閉じる。"""
        if self._cache_conn is not None:
            self._cache_conn.close()
            self._cache_conn = None
        self._session.close()

    def __enter__(self) -> "EstatApiClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _join_codes(codes: str | list[str] | None) -> str | None:
    """地域/時間コードをカンマ区切り文字列に整形する。"""
    if codes is None:
        return None
    if isinstance(codes, str):
        return codes
    return ",".join(str(c) for c in codes)
