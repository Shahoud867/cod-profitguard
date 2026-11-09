.PHONY: setup dev test build seed validate
setup:
	python scripts/setup.py
dev:
	python scripts/dev.py
test:
	.venv/bin/python -m pytest services/api/tests -q
	npm --prefix apps/web test
build:
	npm --prefix apps/web run build
seed:
	.venv/bin/python scripts/seed.py
validate:
	.venv/bin/python scripts/validate_seed.py
