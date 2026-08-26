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


# --- バリデーションテスト (#11) ---

def test_score_invalid_code_format(capsys):
    """--code が 5 桁数字でない場合は SystemExit(2) になること。"""
    with pytest.raises(SystemExit) as exc:
        main(["score", "--code", "ABC", "--life-stage", "single_active"])
    assert exc.value.code == 2


def test_score_code_too_short(capsys):
    """4 桁コードも拒否されること。"""
    with pytest.raises(SystemExit) as exc:
        main(["score", "--code", "1234", "--life-stage", "single_active"])
    assert exc.value.code == 2


def test_ranking_invalid_life_stage(capsys):
    """無効な --life-stage は SystemExit(2) になること。"""
    with pytest.raises(SystemExit) as exc:
        main(["ranking", "--life-stage", "invalid_stage"])
    assert exc.value.code == 2


def test_score_invalid_life_stage(capsys):
    """score コマンドでも無効な --life-stage は SystemExit(2) になること。"""
    with pytest.raises(SystemExit) as exc:
        main(["score", "--code", "01100", "--life-stage", "bad_stage"])
    assert exc.value.code == 2


def test_ranking_invalid_occupation(capsys):
    """無効な --occupation は SystemExit(2) になること。"""
    with pytest.raises(SystemExit) as exc:
        main(["ranking", "--life-stage", "single_active", "--occupation", "wizard"])
    assert exc.value.code == 2


def test_profiles_invalid_life_stage(capsys):
    """profiles コマンドでも無効な --life-stage は SystemExit(2) になること。"""
    with pytest.raises(SystemExit) as exc:
        main(["profiles", "--life-stage", "no_such_stage"])
    assert exc.value.code == 2


# --- #14: ファイル存在チェック・例外ハンドリング ---

def test_missing_indicators_file_returns_exit2(capsys):
    """存在しない --indicators ファイルを指定すると rc=2 でエラーメッセージを出す。"""
    rc = main(["--indicators", "/nonexistent/path.csv",
               "ranking", "--life-stage", "single_active"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "エラー" in err


def test_missing_config_file_returns_exit2(capsys):
    """存在しない --config ファイルを指定すると rc=2 でエラーメッセージを出す。"""
    rc = main(["--config", "/nonexistent/weights.yaml",
               "ranking", "--life-stage", "single_active"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "エラー" in err


def test_verbose_flag_shows_traceback(capsys):
    """--verbose 指定時は rc=2 かつ stderr にトレースバックが出る。"""
    rc = main(["--verbose", "--indicators", "/nonexistent/path.csv",
               "ranking", "--life-stage", "single_active"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "Traceback" in err
