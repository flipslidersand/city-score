"""CLI 統合テスト (#323)。

実際のサンプルデータを使って CLI コマンドを end-to-end 検証する。
"""

import pytest

from city_score.cli import main


def test_ranking_table(capsys):
    rc = main(["ranking", "--life-stage", "single_active", "--top", "5"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "rank" in out
    assert "score" in out


def test_ranking_markdown(capsys):
    rc = main(["ranking", "--life-stage", "family_raising", "--format", "markdown", "--top", "3"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "| rank |" in out
    assert "---" in out


def test_ranking_with_occupation(capsys):
    rc = main(["ranking", "--life-stage", "single_active", "--occupation", "software_engineer", "--top", "5"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "score" in out


def test_score_valid_code(capsys):
    # 01100 (札幌市) はサンプルデータに存在する
    rc = main(["score", "--code", "01100", "--life-stage", "single_active"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "総合スコア" in out


def test_score_invalid_code(capsys):
    rc = main(["score", "--code", "99999", "--life-stage", "single_active"])
    assert rc == 1


def test_profiles_no_stage(capsys):
    rc = main(["profiles"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "single_active" in out
    assert "software_engineer" in out


def test_profiles_with_stage(capsys):
    rc = main(["profiles", "--life-stage", "pre_retirement", "--occupation", "healthcare_worker"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "実効重み" in out
