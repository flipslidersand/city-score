"""気象データ取得スクリプト (#313).

気象庁 過去の気象データ (e-Stat JSON / CSV) から
猛暑日数・豪雪日数・平均気温・日照時間を取得し、
市区町村コード×年度のDataFrameとして返す。

アーキテクチャ:
- JmaClient: 気象庁 CSV エクスポートの薄いラッパー
  URL パターン: https://www.data.jma.go.jp/stats/etrn/view/annually_a.php?prec_no=...
- StationIndex: アメダス地点番号 → 市区町村コード の対応表
- WeatherCollector: 複数地点をバッチ取得してキャッシュ

実ネットワーク不要のスタブモードあり (stub=True)。
API キー不要だが、気象庁サーバーへの過度なアクセスは避けること。
"""

from __future__ import annotations

import csv
import hashlib
import io
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pandas as pd
import requests

# 気象庁 年次統計 CSV URL パターン
# prec_no: 地方気象台コード (2桁), block_no: 観測所番号 (4or5桁)
_JMA_ANNUALLY_URL = (
    "https://www.data.jma.go.jp/stats/etrn/view/"
    "annually_a.php?prec_no={prec_no}&block_no={block_no}&view=p1"
)

_DEFAULT_CACHE = Path.home() / ".cache" / "city_score" / "weather.db"

# 代表的なアメダス地点 → 市区町村コード マッピング（主要47都市）
# (prec_no, block_no, municipality_code, prefecture, name)
STATION_MASTER: list[tuple[str, str, str, str, str]] = [
    ("11", "47412", "01100", "北海道", "札幌"),
    ("14", "47575", "02201", "青森県", "青森"),
    ("33", "47584", "03201", "岩手県", "盛岡"),
    ("34", "47590", "04100", "宮城県", "仙台"),
    ("31", "47582", "05201", "秋田県", "秋田"),
    ("32", "47588", "06201", "山形県", "山形"),
    ("36", "47595", "07201", "福島県", "福島"),
    ("40", "47629", "08201", "茨城県", "水戸"),
    ("41", "47615", "09201", "栃木県", "宇都宮"),
    ("42", "47624", "10201", "群馬県", "前橋"),
    ("43", "47662", "11100", "埼玉県", "さいたま"),
    ("45", "47682", "12100", "千葉県", "千葉"),
    ("44", "47662", "13101", "東京都", "東京"),
    ("46", "47638", "14100", "神奈川県", "横浜"),
    ("54", "47604", "15201", "新潟県", "新潟"),
    ("56", "47607", "16201", "富山県", "富山"),
    ("57", "47605", "17201", "石川県", "金沢"),
    ("58", "47616", "18201", "福井県", "福井"),
    ("49", "47646", "19201", "山梨県", "甲府"),
    ("48", "47610", "20201", "長野県", "長野"),
    ("51", "47654", "21201", "岐阜県", "岐阜"),
    ("50", "47656", "22130", "静岡県", "静岡"),
    ("51", "47636", "23100", "愛知県", "名古屋"),
    ("53", "47651", "24201", "三重県", "津"),
    ("61", "47759", "25201", "滋賀県", "大津"),
    ("62", "47772", "26100", "京都府", "京都"),
    ("62", "47772", "27100", "大阪府", "大阪"),
    ("63", "47770", "28100", "兵庫県", "神戸"),
    ("64", "47780", "29201", "奈良県", "奈良"),
    ("65", "47777", "30201", "和歌山県", "和歌山"),
    ("69", "47746", "31201", "鳥取県", "鳥取"),
    ("68", "47741", "32201", "島根県", "松江"),
    ("66", "47768", "33100", "岡山県", "岡山"),
    ("67", "47765", "34100", "広島県", "広島"),
    ("81", "47762", "35201", "山口県", "山口"),
    ("72", "47895", "36201", "徳島県", "徳島"),
    ("73", "47891", "37201", "香川県", "高松"),
    ("74", "47887", "38201", "愛媛県", "松山"),
    ("74", "47893", "39201", "高知県", "高知"),
    ("82", "47807", "40130", "福岡県", "福岡"),
    ("85", "47813", "41201", "佐賀県", "佐賀"),
    ("84", "47817", "42201", "長崎県", "長崎"),
    ("86", "47819", "43100", "熊本県", "熊本"),
    ("83", "47815", "44201", "大分県", "大分"),
    ("87", "47830", "45201", "宮崎県", "宮崎"),
    ("88", "47827", "46201", "鹿児島県", "鹿児島"),
    ("91", "47936", "47201", "沖縄県", "那覇"),
]


@dataclass
class WeatherRecord:
    """1地点・1年分の気象データ。"""

    code: str  # 市区町村コード
    year: int
    mean_temp: float | None = None       # 年平均気温 (℃)
    hot_days: float | None = None        # 猛暑日数（日最高気温≥35℃の日数）
    heavy_snow_days: float | None = None  # 豪雪日数（積雪30cm以上の日数）
    sunshine_hours: float | None = None  # 年間日照時間 (h)


class JmaClient:
    """気象庁 過去データ CSV 取得クライアント。

    stub=True の場合は実ネットワークを使わず、register_stub で登録した
    DataFrame を返す（テスト・オフライン開発用）。
    """

    def __init__(
        self,
        *,
        stub: bool = False,
        request_interval: float = 1.0,
        timeout: int = 30,
    ):
        self._stub = stub
        self._stubs: dict[tuple[str, str], pd.DataFrame] = {}
        self._interval = request_interval
        self._timeout = timeout
        self._session = requests.Session()
        self._last_req = 0.0

    def register_stub(self, prec_no: str, block_no: str, df: pd.DataFrame) -> None:
        self._stubs[(prec_no, block_no)] = df

    def fetch_annual(self, prec_no: str, block_no: str) -> pd.DataFrame:
        """年次統計 CSV を取得して DataFrame に変換する。

        Returns:
            columns: year, mean_temp, hot_days, heavy_snow_days, sunshine_hours
            すべて数値 (float)、取得不可列は NaN。
        """
        if self._stub:
            return self._stubs.get((prec_no, block_no), pd.DataFrame())

        elapsed = time.time() - self._last_req
        if elapsed < self._interval:
            time.sleep(self._interval - elapsed)

        url = _JMA_ANNUALLY_URL.format(prec_no=prec_no, block_no=block_no)
        resp = self._session.get(url, timeout=self._timeout)
        resp.raise_for_status()
        self._last_req = time.time()

        return _parse_jma_html(resp.text)

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "JmaClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _parse_jma_html(html: str) -> pd.DataFrame:
    """気象庁の年次統計 HTML からデータ行を抽出する。

    気象庁の年次統計ページはHTMLテーブル形式で気象データを含む。
    pandas.read_html でテーブルを抽出し、年/気温/猛暑日数/日照時間を取得する。

    NOTE: 気象庁のHTML構造は予告なく変わる可能性がある（要定期確認）。
    """
    try:
        tables = pd.read_html(io.StringIO(html), header=[0, 1])
    except ValueError:
        return pd.DataFrame()

    # 最大の表を使う（気象データ本体）
    df = max(tables, key=len)
    # 列名をフラット化
    df.columns = [
        "_".join(str(c) for c in col).strip() if isinstance(col, tuple) else str(col)
        for col in df.columns
    ]
    df = df.rename(columns=lambda c: c.strip())

    # 年列を探す
    year_col = next((c for c in df.columns if "年" in c or "year" in c.lower()), None)
    if year_col is None:
        return pd.DataFrame()

    result = pd.DataFrame()
    result["year"] = pd.to_numeric(df[year_col], errors="coerce")

    # 各気象要素を探す（列名の一部マッチ）
    def _find_col(keywords: list[str]) -> str | None:
        for kw in keywords:
            for col in df.columns:
                if kw in col:
                    return col
        return None

    for out_col, keywords in [
        ("mean_temp", ["平均気温", "気温_平均", "年平均"]),
        ("hot_days", ["猛暑日", "35.0以上", "最高≥35"]),
        ("heavy_snow_days", ["30cm以上", "豪雪", "積雪30"]),
        ("sunshine_hours", ["日照時間", "日照_合計"]),
    ]:
        col = _find_col(keywords)
        result[out_col] = pd.to_numeric(df[col], errors="coerce") if col else float("nan")

    return result.dropna(subset=["year"]).reset_index(drop=True)


class WeatherCollector:
    """複数地点の気象データをバッチ取得しキャッシュする。

    Args:
        client: JmaClient インスタンス（省略時は自動生成）
        cache_path: SQLite キャッシュファイル（None でキャッシュ無効）
        stations: 取得対象の地点リスト（省略時は STATION_MASTER 全件）
    """

    def __init__(
        self,
        client: JmaClient | None = None,
        *,
        cache_path: str | Path | None = _DEFAULT_CACHE,
        stations: list[tuple[str, str, str, str, str]] | None = None,
    ):
        self._client = client or JmaClient()
        self._stations = stations if stations is not None else STATION_MASTER
        self._cache_path = Path(cache_path) if cache_path else None
        if self._cache_path:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_cache()

    def _init_cache(self) -> None:
        conn = sqlite3.connect(self._cache_path)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS weather (
                code TEXT, year INTEGER,
                mean_temp REAL, hot_days REAL,
                heavy_snow_days REAL, sunshine_hours REAL,
                fetched_at TEXT,
                PRIMARY KEY (code, year)
            )"""
        )
        conn.commit()
        conn.close()

    def _cache_get(self, code: str) -> pd.DataFrame | None:
        if not self._cache_path:
            return None
        conn = sqlite3.connect(self._cache_path)
        df = pd.read_sql_query(
            "SELECT * FROM weather WHERE code=?", conn, params=(code,)
        )
        conn.close()
        return df if not df.empty else None

    def _cache_put(self, df: pd.DataFrame, code: str) -> None:
        if not self._cache_path or df.empty:
            return
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        df = df.copy()
        df["code"] = code
        df["fetched_at"] = now
        conn = sqlite3.connect(self._cache_path)
        df.to_sql("weather", conn, if_exists="replace", index=False,
                  method="multi")
        conn.commit()
        conn.close()

    def fetch(
        self,
        years: list[int] | None = None,
        *,
        max_missing_rate: float = 0.5,
    ) -> pd.DataFrame:
        """全 stations の気象データを取得して結合する。

        Args:
            years: 取得年リスト（省略時は直近10年）
            max_missing_rate: この割合超の欠損がある地点はスキップ

        Returns:
            code × year の気象指標 DataFrame
        """
        if years is None:
            import datetime
            current = datetime.date.today().year
            years = list(range(current - 10, current))

        frames: list[pd.DataFrame] = []
        for prec_no, block_no, code, _pref, _name in self._stations:
            cached = self._cache_get(code)
            if cached is not None:
                filtered = cached[cached["year"].isin(years)]
                if len(filtered) == len(years):
                    frames.append(filtered)
                    continue

            try:
                df = self._client.fetch_annual(prec_no, block_no)
            except Exception as exc:  # noqa: BLE001
                import warnings
                warnings.warn(f"JMA fetch failed for code={code}: {exc}", stacklevel=2)
                continue

            if df.empty:
                continue

            df["code"] = code
            df = df[df["year"].isin(years)]

            indicator_cols = ["mean_temp", "hot_days", "heavy_snow_days", "sunshine_hours"]
            missing_rate = df[indicator_cols].isna().mean().mean()
            if missing_rate > max_missing_rate:
                import warnings
                warnings.warn(
                    f"code={code}: high missing rate {missing_rate:.0%}, skipping",
                    stacklevel=2,
                )
                continue

            self._cache_put(df, code)
            frames.append(df)

        if not frames:
            return pd.DataFrame(
                columns=["code", "year", "mean_temp", "hot_days",
                         "heavy_snow_days", "sunshine_hours"]
            )

        return (
            pd.concat(frames, ignore_index=True)
            .drop_duplicates(["code", "year"])
            .sort_values(["code", "year"])
            .reset_index(drop=True)
        )
