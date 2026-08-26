"""e-Stat データ取得スクリプト (#314).

e-Stat API v3.0 から city-score の指標に必要な統計テーブルを一括取得する。

対象テーブル（statsDataId と取得指標）:
  T000840001  社会・人口統計体系（市区町村）: 人口・外国人比率・単身世帯比率
  T000310000  住民基本台帳人口移動: 転入超過率（移住者受容度代理）
  0003007907  国勢調査 労働力状態: 高齢者就業率（老後就労）
  0003007907  国勢調査 産業分類: 産業多様性（経済センサス代替）
  0003121999  医療施設調査: 医療施設密度（老後インフラ）

API キーは環境変数 ESTAT_API_KEY から取得。
スタブモードで実ネットワーク不使用の単体テストが可能。
"""

from __future__ import annotations

import math
import os
import weakref
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from ..clients.estat_client import EstatApiClient

# ----- 統計テーブル定義 -----
# (table_id, description, area_class_id, indicator_key, transform)
# transform: API 数値列 → city-score 指標値の変換ロジック (None = 変換なし)

_ENV_KEY = "ESTAT_API_KEY"
_DEFAULT_CACHE = Path.home() / ".cache" / "city_score" / "estat_cache.db"


@dataclass
class StatTable:
    """取得対象の e-Stat 統計テーブル定義。"""

    stats_data_id: str
    description: str
    # 取得して indicator_col に格納する列の e-Stat 数値コード or 名前部分マッチ
    value_key_hint: str
    # 出力列名 (city-score 指標 or 中間列)
    indicator_col: str
    # データ変換: raw Series → indicator Series
    transform: str = "identity"  # "identity" | "per1000" | "shannon" | "invert"
    # 絞り込み用カテゴリコード (cd_cat01 等, None = 全件)
    cd_cat01: str | None = None


# city-score が必要とする統計テーブル一覧
# NOTE: statsDataId は政府統計総合窓口の実IDを使用（要定期確認）
STAT_TABLES: list[StatTable] = [
    StatTable(
        stats_data_id="0003109821",  # 住民基本台帳人口移動報告（市区町村別）
        description="住民基本台帳 転入超過数",
        value_key_hint="転入超過数",
        indicator_col="net_migration_raw",
        transform="identity",
    ),
    StatTable(
        stats_data_id="0003431122",  # 国勢調査 世帯の種類別世帯数（単独世帯）
        description="国勢調査 単独世帯数（中間指標、比率計算用）",
        value_key_hint="単独",
        indicator_col="_single_household_count",
        transform="identity",
        cd_cat01="001",  # 「単独世帯」カテゴリのみ指定
    ),
    StatTable(
        stats_data_id="0003431123",  # 国勢調査 世帯数総数
        description="国勢調査 総世帯数（中間指標、比率計算用）",
        value_key_hint="世帯",
        indicator_col="_total_household_count",
        transform="identity",
    ),
    StatTable(
        stats_data_id="0003555159",  # 住宅・土地統計調査 借家の平均家賃・敷金
        description="住宅・土地統計調査 借家平均家賃（円/月）",
        value_key_hint="平均家賃",
        indicator_col="housing_cost_raw",
        transform="identity",
    ),
    StatTable(
        stats_data_id="0003410378",  # 国勢調査2020 年齢5歳階級・性別就業状態
        description="国勢調査 65歳以上就業率",
        value_key_hint="65歳以上",
        indicator_col="elderly_employment_rate",
        transform="identity",
    ),
    StatTable(
        stats_data_id="0003410379",  # 国勢調査2020 産業(大分類)・従業上の地位別就業者
        description="国勢調査 産業別就業者数（多様性計算用）",
        value_key_hint="産業分類",
        indicator_col="industry_employment_raw",
        transform="shannon",
    ),
    StatTable(
        stats_data_id="0003207854",  # 住民基本台帳 外国人住民数
        description="外国人住民数（移住者受容度代理）",
        value_key_hint="外国人",
        indicator_col="foreign_resident_raw",
        transform="per1000",
    ),
    StatTable(
        stats_data_id="0003276611",  # 医療施設調査 施設数
        description="医療施設数（医療密度計算用）",
        value_key_hint="医療施設",
        indicator_col="medical_facility_raw",
        transform="per10k",
    ),
]


def _shannon_diversity(series: pd.Series) -> float:
    """Series の値（就業者数等）を使いシャノン多様性指数を計算する。"""
    total = series.sum()
    if total <= 0:
        return 0.0
    props = series / total
    return float(-sum(p * math.log(p) for p in props if p > 0))


class EstatCollector:
    """e-Stat 複数テーブルを一括取得し、市区町村×年度の指標 DataFrame を返す。

    Args:
        api_key: e-Stat アプリケーション ID。省略時は環境変数 ESTAT_API_KEY。
        tables: 取得対象テーブル定義（省略時は STAT_TABLES 全件）
        stub: True のときは実ネットワーク不使用（テスト用）
        cache_path: EstatApiClient のSQLite キャッシュパス
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        tables: list[StatTable] | None = None,
        stub: bool = False,
        cache_path: str | Path | None = _DEFAULT_CACHE,
    ):
        key = api_key or os.environ.get(_ENV_KEY, "")
        if not stub and not key:
            raise ValueError(
                f"e-Stat API key required. Set {_ENV_KEY} or pass api_key=..."
            )
        self._client = EstatApiClient(
            api_key=key or "dummy",
            cache_path=cache_path,
            stub=stub,
        )
        self._tables = tables if tables is not None else STAT_TABLES
        # Ensure close() is called even when context manager is not used (#17)
        self._finalizer = weakref.finalize(self, self._client.close)

    # ----- スタブ登録 -----

    def register_stub(self, endpoint: str, response: Any) -> None:
        """テスト用スタブを EstatApiClient に登録する。"""
        self._client.register_stub(endpoint, response)

    # ページサイズ: e-Stat API の 1 リクエストあたり最大 10 万件だが、
    # メモリ・レート配慮のため 10,000 件ずつ取得する。
    _PAGE_SIZE = 10_000

    # ----- 取得 -----

    def fetch_table(
        self,
        table: StatTable,
        *,
        cd_area: str | list[str] | None = None,
        year: int | None = None,
    ) -> pd.DataFrame:
        """1テーブルを取得して market_code × 指標値の DataFrame を返す。

        ページネーション対応: e-Stat API は 1 リクエストあたり最大 10 万件。
        レスポンスの TOTAL_NUMBER / TO_NUMBER を監視し、全件取得するまで
        startPosition を進めてループする。

        Returns:
            columns: code (str), year (int), <indicator_col> (float)
        """
        import warnings

        extra: dict[str, Any] = {}
        if cd_area:
            extra["cdArea"] = cd_area if isinstance(cd_area, str) else ",".join(cd_area)
        if year:
            extra["cdTime"] = str(year)
        if table.cd_cat01:
            extra["cdCat01"] = table.cd_cat01

        all_frames: list[pd.DataFrame] = []
        start_position = 1

        while True:
            try:
                resp = self._client.get_data(
                    table.stats_data_id,
                    meta_get_flg="N",
                    cnt_get_flg="N",
                    start_position=start_position,
                    limit=self._PAGE_SIZE,
                    **extra,
                )
            except Exception as exc:  # noqa: BLE001
                warnings.warn(
                    f"e-Stat fetch failed [{table.stats_data_id}]: {exc}", stacklevel=2
                )
                if not all_frames:
                    return pd.DataFrame(columns=["code", "year", table.indicator_col])
                break

            page_df = self._parse_response(resp, table)
            all_frames.append(page_df)

            # ページネーション終了判定: TOTAL_NUMBER と TO_NUMBER を比較
            try:
                table_inf = (
                    resp.get("GET_STATS_DATA", {})
                    .get("STATISTICAL_DATA", {})
                    .get("TABLE_INF", {})
                )
                total_number = int(table_inf.get("TOTAL_NUMBER", 0))
                to_number = int(table_inf.get("TO_NUMBER", 0))
            except (TypeError, ValueError):
                break  # パース不能な場合はページング終了

            if total_number == 0 or to_number >= total_number:
                break

            start_position = to_number + 1

        if not all_frames:
            return pd.DataFrame(columns=["code", "year", table.indicator_col])

        return pd.concat(all_frames, ignore_index=True)

    def _parse_response(self, resp: dict[str, Any], table: StatTable) -> pd.DataFrame:
        """e-Stat API レスポンスを code × year × 指標値 DataFrame に変換する。"""
        try:
            data_inf = resp.get("GET_STATS_DATA", {}).get("STATISTICAL_DATA", {})
            data_obj = data_inf.get("DATA_INF", {})
            values = data_obj.get("VALUE", [])
        except (AttributeError, KeyError):
            return pd.DataFrame(columns=["code", "year", table.indicator_col])

        if not values:
            return pd.DataFrame(columns=["code", "year", table.indicator_col])

        rows = []
        for v in values:
            code = str(v.get("@area", "")).zfill(5)
            time_val = str(v.get("@time", ""))
            # e-Stat の時間コード: "2020CY00" → 2020
            try:
                yr = int(time_val[:4])
            except ValueError:
                yr = 0
            try:
                val = float(str(v.get("$", "")).replace(",", ""))
            except ValueError:
                val = float("nan")
            rows.append({"code": code, "year": yr, "_raw": val})

        df = pd.DataFrame(rows)
        if df.empty:
            return pd.DataFrame(columns=["code", "year", table.indicator_col])

        df = self._apply_transform(df, table)
        df = df.rename(columns={"_raw": table.indicator_col})
        return df[["code", "year", table.indicator_col]].dropna(subset=["code", "year"])

    def _apply_transform(self, df: pd.DataFrame, table: StatTable) -> pd.DataFrame:
        """StatTable.transform に応じて _raw 列を変換する。"""
        if table.transform == "identity":
            pass
        elif table.transform == "per1000":
            # 人口 1000人あたりに変換（population 列が必要）
            if "population" not in df.columns:
                raise NotImplementedError(
                    f"per1000 transform requires a 'population' column in the DataFrame "
                    f"(table={table.stats_data_id}, col={table.indicator_col}). "
                    "Merge population data before calling _apply_transform."
                )
            pop = df["population"]
            df["_raw"] = df["_raw"].where(pop <= 0, df["_raw"] / (pop / 1000.0))
        elif table.transform == "per10k":
            # 人口 10000人あたりに変換（population 列が必要）
            if "population" not in df.columns:
                raise NotImplementedError(
                    f"per10k transform requires a 'population' column in the DataFrame "
                    f"(table={table.stats_data_id}, col={table.indicator_col}). "
                    "Merge population data before calling _apply_transform."
                )
            pop = df["population"]
            df["_raw"] = df["_raw"].where(pop <= 0, df["_raw"] / (pop / 10000.0))
        elif table.transform == "shannon":
            # 産業多様性: code × year でグループ化してシャノン指数を計算
            def _shannon_by_group(grp: pd.DataFrame) -> float:
                return _shannon_diversity(grp["_raw"].dropna())
            df = (
                df.groupby(["code", "year"])
                .apply(_shannon_by_group, include_groups=False)
                .reset_index()
                .rename(columns={0: "_raw"})
            )
        elif table.transform == "invert":
            df["_raw"] = -df["_raw"]
        return df

    def fetch_all(
        self,
        *,
        cd_area: str | list[str] | None = None,
        year: int | None = None,
    ) -> pd.DataFrame:
        """STAT_TABLES 全件を取得してマージした DataFrame を返す。

        Returns:
            code × year の全指標列 DataFrame（欠損は NaN）
        """
        frames: list[pd.DataFrame] = []
        for table in self._tables:
            df = self.fetch_table(table, cd_area=cd_area, year=year)
            frames.append(df)

        if not frames:
            return pd.DataFrame(columns=["code", "year"])

        result = frames[0]
        for df in frames[1:]:
            result = result.merge(df, on=["code", "year"], how="outer")

        # 単独世帯比率の計算（中間列から最終指標へ）
        if "_single_household_count" in result.columns and "_total_household_count" in result.columns:
            total = result["_total_household_count"]
            single = result["_single_household_count"]
            result["single_household_ratio"] = (single / total * 100).where(total > 0, None)
            result = result.drop(columns=["_single_household_count", "_total_household_count"])

        return result.sort_values(["code", "year"]).reset_index(drop=True)

    def close(self) -> None:
        # Deactivate the weakref finalizer so close() is not called twice (#17)
        if hasattr(self, "_finalizer") and self._finalizer.alive:
            self._finalizer.detach()
        self._client.close()

    def __enter__(self) -> "EstatCollector":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
