"""市区町村マスタデータ (#312).

city-score の正規化キー ``area_code``（市区町村 5 桁 JIS コード, JIS X 0402）
に対応する基礎マスタ（コード / 名前 / 都道府県 / 人口 / 緯度経度）を提供する。

方針（``docs/data-catalog.md`` §1 と整合）:
- 正規化キーは ``code``（5 桁 JIS コード）。都道府県 2 桁 + 市区町村 3 桁。
- リポジトリには小さなサンプル（都道府県庁所在市＋東京 23 区の一部, 数十件）を
  同梱する。全市区町村（約 1,700 件）はサンプルではなく、e-Stat の
  ``getMetaInfo`` 地域軸から取得する設計（``build_municipalities_from_estat``）。
- 名前ゆれ（全角空白・異体字・ヶ/ケ 等）は ``normalize_municipality_name`` で吸収。

出典（人口・座標）: 政府統計の総合窓口 (e-Stat) 等の公開値を丸めたサンプル。
実運用では最新値を e-Stat から取得して更新する（**要検証**）。
"""

from __future__ import annotations

import unicodedata
from importlib import resources
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:  # pragma: no cover
    from city_score.clients.estat_client import EstatApiClient

# DataFrame の確定カラム順・型。
COLUMNS = ["code", "name", "prefecture", "population", "latitude", "longitude"]
_DTYPES = {
    "code": "string",
    "name": "string",
    "prefecture": "string",
    "population": "Int64",
    "latitude": "float64",
    "longitude": "float64",
}

_SAMPLE_RESOURCE = "municipalities_sample.csv"

# 名前正規化で置換する文字（表記ゆれ吸収）。
# ケ/ヶ は自治体名で混在しやすい（例: 茅ヶ崎 / 茅ケ崎）。小書き ヶ に寄せる。
_NAME_CHAR_MAP = {
    "ケ": "ヶ",
    "ﾉ": "の",
    "髙": "高",  # はしごだか -> 高
    "﨑": "崎",  # たつさき -> 崎
}


def normalize_municipality_name(name: str) -> str:
    """市区町村名の表記ゆれを正規化する。

    - Unicode NFKC 正規化（全角英数・互換文字を統一）。
    - 前後・内部の空白（全角/半角）を除去。
    - ケ↔ヶ、異体字（髙/﨑 等）を代表字へ寄せる。

    Args:
        name: 生の市区町村名。

    Returns:
        正規化後の名前。``None``/空は空文字を返す。
    """
    if not name:
        return ""
    text = unicodedata.normalize("NFKC", str(name))
    # NFKC 後に残る空白（半角化されている）をすべて除去。
    text = "".join(ch for ch in text if not ch.isspace())
    for src, dst in _NAME_CHAR_MAP.items():
        text = text.replace(src, dst)
    return text


def _coerce_frame(df: pd.DataFrame) -> pd.DataFrame:
    """列順・型を確定し、コードを 5 桁ゼロ埋めして整える。"""
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"必須カラムが不足しています: {missing}")
    df = df[COLUMNS].copy()
    # コードは文字列 5 桁ゼロ埋め（例: 1100 -> "01100"）。
    df["code"] = (
        df["code"].astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    )
    df["code"] = df["code"].str.zfill(5)
    df["name"] = df["name"].astype("string").str.strip()
    df["prefecture"] = df["prefecture"].astype("string").str.strip()
    return df.astype(_DTYPES).reset_index(drop=True)


def _validate(df: pd.DataFrame) -> None:
    """マスタの整合性を検証する（コード一意・形式・非空）。"""
    dupes = df["code"][df["code"].duplicated()].tolist()
    if dupes:
        raise ValueError(f"市区町村コードが重複しています: {sorted(set(dupes))}")
    bad = df.loc[~df["code"].str.fullmatch(r"\d{5}"), "code"].tolist()
    if bad:
        raise ValueError(f"5 桁数字でないコードがあります: {bad}")
    if df["name"].isna().any() or (df["name"].str.len() == 0).any():
        raise ValueError("空の市区町村名があります。")


def load_municipalities(
    csv_path: str | Any | None = None,
    *,
    normalize_names: bool = True,
) -> pd.DataFrame:
    """市区町村マスタを DataFrame で読み込む。

    Args:
        csv_path: 読み込む CSV パス。``None`` の場合はパッケージ同梱の
            サンプル (``municipalities_sample.csv``) を使う。
        normalize_names: 名前正規化列 ``name_normalized`` を付与するか。

    Returns:
        カラム ``code, name, prefecture, population, latitude, longitude``
        （+ ``normalize_names`` 時は ``name_normalized``）を持つ DataFrame。
        コードは 5 桁ゼロ埋め文字列・一意。

    Raises:
        ValueError: コード重複・形式不正・空名などの整合性エラー。
    """
    if csv_path is None:
        with resources.files("city_score.data").joinpath(_SAMPLE_RESOURCE).open(
            "r", encoding="utf-8"
        ) as fh:
            df = pd.read_csv(fh, dtype={"code": "string"})
    else:
        df = pd.read_csv(csv_path, dtype={"code": "string"})

    df = _coerce_frame(df)
    _validate(df)

    if normalize_names:
        df["name_normalized"] = df["name"].map(normalize_municipality_name)
    return df


def build_municipalities_from_estat(
    client: "EstatApiClient",
    stats_data_id: str,
    *,
    area_class_id: str = "area",
    municipal_level: str | None = None,
) -> pd.DataFrame:
    """e-Stat の地域メタ情報から市区町村マスタ（コード・名前）を構築する。

    フル取得用のヘルパ。人口・緯度経度は含まないため、必要に応じて
    別統計表（国勢調査）や外部座標データと結合する（**要検証**）。

    Args:
        client: ``EstatApiClient``。
        stats_data_id: 地域軸を持つ統計表 ID。
        area_class_id: 地域軸の分類 ID（既定 ``"area"``）。
        municipal_level: 市区町村レベルの ``@level`` 値。指定時はその
            レベルのみに絞り込む（**要検証**: level 値は表依存）。

    Returns:
        少なくとも ``code, name`` を持つ DataFrame（他カラムは NA）。
    """
    rows = client.list_municipalities(stats_data_id, area_class_id=area_class_id)
    if municipal_level is not None:
        rows = [r for r in rows if r.get("level") == municipal_level]

    df = pd.DataFrame(rows, columns=["code", "name", "level", "parent"])
    df["prefecture"] = pd.NA
    df["population"] = pd.NA
    df["latitude"] = pd.NA
    df["longitude"] = pd.NA
    df = _coerce_frame(df)
    _validate(df)
    df["name_normalized"] = df["name"].map(normalize_municipality_name)
    return df
