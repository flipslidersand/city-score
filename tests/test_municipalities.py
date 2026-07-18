"""市区町村マスタのスモークテスト (#312)。"""

from city_score.data.municipalities import load_municipalities


def test_load_columns_and_uniqueness():
    df = load_municipalities()
    assert len(df) > 0
    for col in ("code", "name", "prefecture", "population", "name_normalized"):
        assert col in df.columns
    # コードは一意
    assert df["code"].is_unique


def test_codes_are_5_digit_strings():
    df = load_municipalities()
    codes = df["code"].astype(str)
    assert (codes.str.len() == 5).all()
