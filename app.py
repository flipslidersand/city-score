"""city-score — Streamlit Cloud エントリポイント.

Streamlit Cloud はデフォルトでリポジトリルートの app.py を探す。
実装は src/ui/streamlit_app.py に集約しているため、ここからそちらを呼び出す。
"""

from src.ui.streamlit_app import main

if __name__ == "__main__":
    main()
