"""city-score CLI (#319)。

サブコマンド:
- ``ranking``  : プロファイル別の居住地ランキングを出力（markdown / table）
- ``score``    : 単一市区町村のスコアと指標内訳を表示
- ``profiles`` : 利用可能なライフステージ・職種と実効重みを表示

指標データは既定で同梱の合成サンプル（``sample_indicators.synthetic.csv``、
デモ用・要検証）を使う。``--indicators`` で実データ CSV を差し替え可能。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .data.municipalities import load_municipalities
from .scoring.engine import ScoringEngine
from .scoring.profiles import load_weights_config

DEFAULT_INDICATORS = (
    Path(__file__).resolve().parent / "data" / "sample_indicators.synthetic.csv"
)


def _load_indicators(path: str | Path | None) -> pd.DataFrame:
    p = Path(path) if path else DEFAULT_INDICATORS
    df = pd.read_csv(p, dtype={"code": str})
    if "name" not in df.columns or "prefecture" not in df.columns:
        muni = load_municipalities()[["code", "name", "prefecture"]]
        muni["code"] = muni["code"].astype(str)
        df = df.merge(muni, on="code", how="left")
    return df


def _to_markdown(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |",
             "| " + " | ".join("---" for _ in cols) + " |"]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    return "\n".join(lines)


def cmd_ranking(args: argparse.Namespace) -> int:
    engine = ScoringEngine(load_weights_config(args.config))
    inds = _load_indicators(args.indicators)
    result = engine.score(
        inds, life_stage=args.life_stage, occupation=args.occupation
    )
    top = result.head(args.top)
    view = top[["rank", "name", "prefecture", "score"]]
    if args.format == "markdown":
        print(f"# 居住地ランキング — {args.life_stage} / {args.occupation}\n")
        print(_to_markdown(view))
        print("\n> データ: 合成サンプル（要検証）。実データは --indicators で差し替え。")
    else:
        print(view.to_string(index=False))
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    engine = ScoringEngine(load_weights_config(args.config))
    inds = _load_indicators(args.indicators)
    result = engine.score(
        inds, life_stage=args.life_stage, occupation=args.occupation
    )
    row = result[result["code"] == str(args.code)] if "code" in result else None
    if row is None or row.empty:
        print(f"見つかりません: code={args.code}")
        return 1
    r = row.iloc[0]
    print(f"{r['name']}（{r.get('prefecture','')}） code={r['code']}")
    print(f"総合スコア: {r['score']}  順位: {r['rank']}/{len(result)}")
    cfg = load_weights_config(args.config)
    detail = inds[inds["code"].astype(str) == str(args.code)]
    if not detail.empty:
        print("--- 指標内訳（生値）---")
        for k in cfg.indicators:
            if k in detail.columns:
                print(f"  {k}: {detail.iloc[0][k]}")
    return 0


def cmd_profiles(args: argparse.Namespace) -> int:
    cfg = load_weights_config(args.config)
    print("life_stages:", ", ".join(cfg.life_stages))
    print("occupations:", ", ".join(cfg.occupations))
    if args.life_stage:
        w = cfg.effective_weights(args.life_stage, args.occupation)
        print(f"\n実効重み ({args.life_stage} / {args.occupation}):")
        for k, v in w.items():
            print(f"  {k}: {v:.3f}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="city-score", description="居住地スコアリング")
    p.add_argument("--config", default=None, help="重み設定 YAML")
    p.add_argument("--indicators", default=None, help="指標データ CSV")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("ranking", help="ランキング出力")
    r.add_argument("--life-stage", required=True)
    r.add_argument("--occupation", default="default")
    r.add_argument("--top", type=int, default=20)
    r.add_argument("--format", choices=["markdown", "table"], default="table")
    r.set_defaults(func=cmd_ranking)

    s = sub.add_parser("score", help="単一地域スコア")
    s.add_argument("--code", required=True)
    s.add_argument("--life-stage", required=True)
    s.add_argument("--occupation", default="default")
    s.set_defaults(func=cmd_score)

    pr = sub.add_parser("profiles", help="プロファイル一覧・重み")
    pr.add_argument("--life-stage", default=None)
    pr.add_argument("--occupation", default="default")
    pr.set_defaults(func=cmd_profiles)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
