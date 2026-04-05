.PHONY: dev dev-setup
dev-setup:
	temporal server start-dev
	temporal server start-dev --ui-port 8080

dev:
	source env/bin/activate
	python3 worker.py

mock:
	uv run python -m uvicorn mock_environment.main:app --port 9999