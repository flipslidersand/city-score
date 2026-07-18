.PHONY: help dev test lint fmt clean

PYTHON ?= python3

help:
	@echo "make dev    - 開発用依存を含めてインストール (editable)"
	@echo "make test   - pytest を実行"
	@echo "make lint   - black --check でフォーマット確認"
	@echo "make fmt    - black でフォーマット適用"
	@echo "make clean  - キャッシュ類を削除"

dev:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m black --check src tests

fmt:
	$(PYTHON) -m black src tests

clean:
	rm -rf .pytest_cache .coverage htmlcov coverage.xml
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
