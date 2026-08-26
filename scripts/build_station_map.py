#!/usr/bin/env python3
"""市区町村コード → 最近傍 AMeDAS 地点 マッピング生成スクリプト (#7).

使い方:
    python scripts/build_station_map.py [--out config/municipality_station_map_full.json]

入力:
    config/amedas_stations.json  — AMeDAS 地点マスタ
    (実データがない場合は都道府県の代表地点から推定)

出力:
    config/municipality_station_map_full.json  — 市区町村コード → 地点ID マッピング
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

# 都道府県コード (2桁) → 代表的な緯度経度（市区町村データがない場合のフォールバック用）
# 実際の使用では政府統計の市区町村座標データを使うこと
PREFECTURE_CENTROIDS: dict[str, tuple[float, float]] = {
    "01": (43.06, 141.35),  # 北海道
    "02": (40.82, 140.74),  # 青森
    "03": (39.70, 141.17),  # 岩手
    "04": (38.27, 140.87),  # 宮城
    "05": (39.72, 140.10),  # 秋田
    "06": (38.25, 140.34),  # 山形
    "07": (37.76, 140.47),  # 福島
    "08": (36.38, 140.47),  # 茨城
    "09": (36.55, 139.87),  # 栃木
    "10": (36.39, 139.06),  # 群馬
    "11": (36.14, 139.39),  # 埼玉
    "12": (35.61, 140.12),  # 千葉
    "13": (35.69, 139.69),  # 東京
    "14": (35.44, 139.64),  # 神奈川
    "15": (37.90, 139.02),  # 新潟
    "16": (36.70, 137.21),  # 富山
    "17": (36.59, 136.63),  # 石川
    "18": (36.07, 136.22),  # 福井
    "19": (35.66, 138.57),  # 山梨
    "20": (36.66, 138.20),  # 長野
    "21": (35.42, 136.76),  # 岐阜
    "22": (34.98, 138.40),  # 静岡
    "23": (35.16, 136.96),  # 愛知
    "24": (34.73, 136.52),  # 三重
    "25": (35.00, 135.87),  # 滋賀
    "26": (35.01, 135.73),  # 京都
    "27": (34.68, 135.52),  # 大阪
    "28": (34.69, 135.18),  # 兵庫
    "29": (34.69, 135.83),  # 奈良
    "30": (34.23, 135.17),  # 和歌山
    "31": (35.50, 134.24),  # 鳥取
    "32": (35.47, 133.05),  # 島根
    "33": (34.66, 133.92),  # 岡山
    "34": (34.40, 132.46),  # 広島
    "35": (34.18, 131.47),  # 山口
    "36": (34.07, 134.55),  # 徳島
    "37": (34.34, 134.04),  # 香川
    "38": (33.84, 132.78),  # 愛媛
    "39": (33.56, 133.53),  # 高知
    "40": (33.58, 130.40),  # 福岡
    "41": (33.26, 130.30),  # 佐賀
    "42": (32.73, 129.87),  # 長崎
    "43": (32.80, 130.70),  # 熊本
    "44": (33.24, 131.62),  # 大分
    "45": (31.94, 131.42),  # 宮崎
    "46": (31.56, 130.55),  # 鹿児島
    "47": (26.20, 127.69),  # 沖縄
}

# 実際の市区町村データがない場合に使うスタブ（各都道府県の代表市区町村コード）
# 市区町村コード 6桁: 都道府県2桁 + 市区町村4桁
# 実際には総務省が提供する全1,741市区町村のデータを使うこと
def _generate_stub_municipalities() -> list[dict]:
    """都道府県代表地点からスタブ市区町村リストを生成する（開発・テスト用）。"""
    stubs = []
    for pref_code, (lat, lon) in PREFECTURE_CENTROIDS.items():
        # 各都道府県に最低1つの代表コードを追加
        muni_code = f"{pref_code}0000"
        stubs.append({"code": muni_code, "lat": lat, "lon": lon, "prefecture": pref_code})
    return stubs


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """2点間のハーバーサイン距離 (km) を計算する。"""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def find_nearest_station(
    lat: float,
    lon: float,
    stations: list[dict],
) -> tuple[dict, float]:
    """最近傍の AMeDAS 地点と距離 (km) を返す。"""
    best_station = stations[0]
    best_dist = float("inf")
    for st in stations:
        d = haversine_km(lat, lon, st["lat"], st["lon"])
        if d < best_dist:
            best_dist = d
            best_station = st
    return best_station, best_dist


def build_mapping(
    stations_path: Path,
    municipalities: list[dict] | None = None,
) -> dict:
    """AMeDAS 地点と市区町村リストからマッピングを構築する。

    Args:
        stations_path: amedas_stations.json のパス
        municipalities: {"code": str, "lat": float, "lon": float} のリスト。
                        None の場合はスタブデータを使用。

    Returns:
        municipality_station_map の辞書
    """
    with stations_path.open(encoding="utf-8") as f:
        station_data = json.load(f)

    stations = station_data["stations"]

    if municipalities is None:
        municipalities = _generate_stub_municipalities()

    mappings: dict[str, dict] = {}
    covered = 0

    for muni in municipalities:
        code = muni["code"]
        lat = muni.get("lat")
        lon = muni.get("lon")

        if lat is None or lon is None:
            # 座標なし → 都道府県代表地点を使う
            pref_code = code[:2]
            centroid = PREFECTURE_CENTROIDS.get(pref_code)
            if centroid is None:
                continue
            lat, lon = centroid

        station, dist_km = find_nearest_station(lat, lon, stations)
        mappings[code] = {
            "station_id": station["station_id"],
            "station_name": station["name"],
            "distance_km": round(dist_km, 2),
        }
        covered += 1

    total = len(municipalities)
    coverage_rate = covered / total if total > 0 else 0.0

    return {
        "version": "2024-01",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_municipalities": total,
        "coverage_rate": round(coverage_rate, 4),
        "mappings": mappings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="市区町村 → AMeDAS 地点マッピング生成")
    parser.add_argument(
        "--stations",
        type=Path,
        default=Path("config/amedas_stations.json"),
        help="AMeDAS 地点マスタ JSON (default: config/amedas_stations.json)",
    )
    parser.add_argument(
        "--municipalities",
        type=Path,
        default=None,
        help="市区町村座標 JSON（省略時はスタブデータを使用）",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("config/municipality_station_map_full.json"),
        help="出力先 JSON (default: config/municipality_station_map_full.json)",
    )
    args = parser.parse_args()

    if not args.stations.exists():
        print(f"ERROR: stations file not found: {args.stations}", file=sys.stderr)
        sys.exit(1)

    municipalities: list[dict] | None = None
    if args.municipalities and args.municipalities.exists():
        with args.municipalities.open(encoding="utf-8") as f:
            municipalities = json.load(f)
        print(f"Loaded {len(municipalities)} municipalities from {args.municipalities}")
    else:
        print("Municipality data not provided, using stub data (47 prefectural representatives)")

    mapping = build_mapping(args.stations, municipalities)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)

    print(
        f"Written: {args.out}\n"
        f"  municipalities: {mapping['total_municipalities']}\n"
        f"  coverage_rate:  {mapping['coverage_rate']:.1%}"
    )


if __name__ == "__main__":
    main()
