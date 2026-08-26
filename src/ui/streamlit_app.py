"""city-score Streamlit UI (#321/#322).

3ページ構成:
1. ランキング — プロファイル別上位 N 都市とレーダーチャート比較
2. 個別スコア — 市区町村コードで1都市の指標内訳をレーダー表示
3. プロファイル提案 — ライフステージ/職種を入力して最適居住地を推薦

起動:
    streamlit run src/ui/streamlit_app.py
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# パッケージは src/ 配下なので sys.path 調整が必要な場合がある
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from city_score.scoring.engine import ScoringEngine  # noqa: E402
from city_score.scoring.profiles import load_weights_config  # noqa: E402

INDICATOR_LABELS = {
    "career_sustainability": "キャリア持続性",
    "elderly_work_opportunity": "老後就労機会",
    "life_cost_efficiency": "生活コスト効率",
    "social_connectedness": "社会的つながり",
    "climate_comfort": "気候快適性",
    "migrant_openness": "移住者受容度",
}

LIFE_STAGE_LABELS = {
    "student_newgrad": "学生・新卒",
    "family_raising": "子育て世代",
    "single_active": "独身アクティブ",
    "pre_retirement": "定年前",
    "retired": "定年後",
}

OCCUPATION_LABELS = {
    "software_engineer": "ソフトウェアエンジニア",
    "civil_servant": "公務員",
    "healthcare_worker": "医療・福祉従事者",
    "default": "その他",
}

_INDICATORS = list(INDICATOR_LABELS.keys())
_DATA_PATH = ROOT / "src" / "city_score" / "data" / "sample_indicators.synthetic.csv"


def _get_data_timestamp() -> str:
    """データファイルのタイムスタンプを取得して表示用に整形."""
    if _DATA_PATH.exists():
        mtime = os.path.getmtime(_DATA_PATH)
        dt = datetime.fromtimestamp(mtime)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return "不明"


@st.cache_data
def _load_data() -> pd.DataFrame:
    df = pd.read_csv(_DATA_PATH, dtype={"code": str})
    muni_path = ROOT / "src" / "city_score" / "data" / "municipalities_sample.csv"
    if muni_path.exists():
        muni = pd.read_csv(muni_path, dtype={"code": str})[["code", "name", "prefecture"]]
        df = df.merge(muni, on="code", how="left")
    return df


@st.cache_resource
def _engine() -> ScoringEngine:
    return ScoringEngine(load_weights_config())


def _radar(rows: list[dict], title: str = "") -> go.Figure:
    labels = list(INDICATOR_LABELS.values())
    fig = go.Figure()
    colors = ["#4C78A8", "#F58518", "#E45756", "#72B7B2", "#54A24B"]
    for i, row in enumerate(rows):
        values = [row.get(k, 0) for k in _INDICATORS]
        values_closed = values + [values[0]]
        labels_closed = labels + [labels[0]]
        fig.add_trace(
            go.Scatterpolar(
                r=values_closed,
                theta=labels_closed,
                fill="toself",
                name=row.get("name", f"都市{i+1}"),
                line_color=colors[i % len(colors)],
                opacity=0.7,
            )
        )
    fig.update_layout(
        title=title,
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        showlegend=True,
        height=420,
        margin=dict(t=60, b=20, l=20, r=20),
    )
    return fig


# ──────────────────────────────────────────────
# Page 1: ランキング
# ──────────────────────────────────────────────
def page_ranking() -> None:
    st.header("居住地ランキング")
    col1, col2, col3 = st.columns(3)
    life_stage = col1.selectbox(
        "ライフステージ",
        list(LIFE_STAGE_LABELS.keys()),
        format_func=LIFE_STAGE_LABELS.get,
    )
    occupation = col2.selectbox(
        "職種",
        list(OCCUPATION_LABELS.keys()),
        format_func=OCCUPATION_LABELS.get,
    )
    top_n = col3.slider("上位 N 件", 5, 50, 20)

    df = _load_data()
    engine = _engine()
    result = engine.score(df, life_stage=life_stage, occupation=occupation)
    top = result.head(top_n).copy()

    # スコア列のみ表示
    display_cols = ["rank", "name", "prefecture", "score"]
    st.dataframe(
        top[display_cols],
        use_container_width=True,
        hide_index=True,
        column_config={"score": st.column_config.NumberColumn("スコア", format="%.1f")},
    )

    # 上位 3 都市のレーダー比較
    st.subheader("上位 3 都市 指標レーダー")
    top3 = top.head(3)
    radar_rows = []
    for _, row in top3.iterrows():
        raw = df[df["code"] == row["code"]].iloc[0].to_dict()
        raw["name"] = row["name"]
        radar_rows.append(raw)
    if radar_rows:
        st.plotly_chart(_radar(radar_rows, "上位3都市 指標比較"), use_container_width=True)


# ──────────────────────────────────────────────
# Page 2: 個別スコア
# ──────────────────────────────────────────────
def page_individual() -> None:
    st.header("個別スコア")
    df = _load_data()
    if "name" in df.columns and "code" in df.columns:
        df_display = df[["code", "name", "prefecture"]].fillna("")
        df_display["display"] = df_display.apply(
            lambda r: f"{r['name']}（{r['prefecture']}）" if r['prefecture'] else r['name'],
            axis=1
        )
        display_list = df_display["display"].tolist()
        code_list = df_display["code"].tolist()
        selected_display = st.selectbox("市区町村", display_list)
        selected_idx = display_list.index(selected_display)
        selected_code = code_list[selected_idx]
    else:
        selected_code = st.text_input("市区町村コード（例: 13101）", value="13101")

    col1, col2 = st.columns(2)
    life_stage = col1.selectbox(
        "ライフステージ",
        list(LIFE_STAGE_LABELS.keys()),
        format_func=LIFE_STAGE_LABELS.get,
        key="ind_ls",
    )
    occupation = col2.selectbox(
        "職種",
        list(OCCUPATION_LABELS.keys()),
        format_func=OCCUPATION_LABELS.get,
        key="ind_occ",
    )

    engine = _engine()
    result = engine.score(df, life_stage=life_stage, occupation=occupation)
    row = result[result["code"] == str(selected_code)]
    if row.empty:
        st.warning("該当する市区町村が見つかりません")
        return

    r = row.iloc[0]
    st.metric("総合スコア", f"{r['score']:.1f}", f"全国 {r['rank']}位 / {len(result)}都市中")

    raw = df[df["code"] == str(selected_code)]
    if not raw.empty:
        raw_row = raw.iloc[0].to_dict()
        raw_row["name"] = r.get("name", selected_code)
        st.plotly_chart(_radar([raw_row], f"{r.get('name', selected_code)} 指標内訳"), use_container_width=True)

        st.subheader("指標詳細（生値）")
        detail = {
            INDICATOR_LABELS[k]: f"{raw_row[k]:.1f}"
            for k in _INDICATORS
            if k in raw_row
        }
        st.table(pd.DataFrame.from_dict(detail, orient="index", columns=["値"]))


# ──────────────────────────────────────────────
# Page 3: プロファイル提案 (#322)
# ──────────────────────────────────────────────
def page_recommend() -> None:
    st.header("プロファイル入力 → 最適居住地提案")
    st.caption("ライフステージ・職種・主観スコアを入力すると、あなたに最適な居住地を提案します。")

    col1, col2 = st.columns(2)
    life_stage = col1.selectbox(
        "ライフステージ",
        list(LIFE_STAGE_LABELS.keys()),
        format_func=LIFE_STAGE_LABELS.get,
        key="rec_ls",
    )
    occupation = col2.selectbox(
        "職種",
        list(OCCUPATION_LABELS.keys()),
        format_func=OCCUPATION_LABELS.get,
        key="rec_occ",
    )

    with st.expander("主観スコアを追加（任意）"):
        st.caption("特定の都市に対する主観的な印象（0〜100）を入力すると、最終スコアにブレンドされます。")
        subj_code = st.text_input("市区町村コード", value="", placeholder="13101")
        subj_score_val = st.slider("主観スコア", 0, 100, 50, key="subj_score")
        alpha = st.slider("主観ブレンド係数 α", 0.0, 0.5, 0.2, step=0.05)

    subjective: dict[str, float] = {}
    if subj_code.strip():
        subjective[subj_code.strip()] = float(subj_score_val)

    df = _load_data()
    engine = _engine()
    result = engine.score(
        df,
        life_stage=life_stage,
        occupation=occupation,
        subjective=subjective or None,
        alpha=alpha,
    )
    top10 = result.head(10)

    st.subheader("あなたにおすすめの居住地 Top 10")
    st.dataframe(
        top10[["rank", "name", "prefecture", "score"]],
        use_container_width=True,
        hide_index=True,
        column_config={"score": st.column_config.NumberColumn("スコア", format="%.1f")},
    )

    cfg = load_weights_config()
    weights = cfg.effective_weights(life_stage, occupation)
    st.subheader("あなたのプロファイル重み")
    w_df = pd.DataFrame(
        [{"指標": INDICATOR_LABELS[k], "重み": f"{v:.3f}"} for k, v in weights.items()]
    )
    st.dataframe(w_df, use_container_width=True, hide_index=True)

    radar_rows = []
    for _, row in top10.head(3).iterrows():
        raw = df[df["code"] == row["code"]].iloc[0].to_dict()
        raw["name"] = row["name"]
        radar_rows.append(raw)
    if radar_rows:
        st.plotly_chart(_radar(radar_rows, "推薦上位3都市 比較"), use_container_width=True)


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main() -> None:
    st.set_page_config(
        page_title="city-score",
        page_icon="🏙️",
        layout="wide",
    )
    st.title("🏙️ city-score — 居住地スコアリング")

    page = st.sidebar.radio(
        "ページ",
        ["ランキング", "個別スコア", "プロファイル提案"],
        label_visibility="collapsed",
    )

    st.sidebar.caption(
        "**city-score** は独自指標（キャリア持続性・生活コスト効率・老後就労等）で"
        "日本全国の市区町村を評価するツールです。\n\n"
        "現在のデータは**合成サンプル**です。実データは `--indicators` で差し替え可能です。"
    )

    st.sidebar.divider()
    st.sidebar.caption(f"📊 データ更新日時: {_get_data_timestamp()}")
    st.sidebar.caption("⚠️ 注：現在のデータは検証用の合成データです")

    if page == "ランキング":
        page_ranking()
    elif page == "個別スコア":
        page_individual()
    else:
        page_recommend()


if __name__ == "__main__":
    main()
