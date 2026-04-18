PYTHON = env/bin/python

.PHONY: up dev-setup dev mock worker api ui start transition state transitions audit

down:
	@echo "Stopping existing processes..."
	@-lsof -ti :7233 | xargs kill -9 2>/dev/null || true
	@-lsof -ti :8080 | xargs kill -9 2>/dev/null || true
	@-lsof -ti :9999 | xargs kill -9 2>/dev/null || true
	@-lsof -ti :8000 | xargs kill -9 2>/dev/null || true
	@-lsof -ti :3000 | xargs kill -9 2>/dev/null || true
	@sleep 1

up: down
	@echo "Starting Temporal, mock server, worker, API server, and UI..."
	temporal server start-dev --ui-port 8080 & \
	echo "Waiting for Temporal server to be ready..." && \
	until nc -z localhost 7233 2>/dev/null; do sleep 1; done && \
	echo "Temporal server is ready." && \
	$(PYTHON) -m uvicorn mock_environment.main:app --port 9999 & \
	$(PYTHON) worker.py & \
	$(PYTHON) -m uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload & \
	cd ui && bun dev & \
	wait

dev-setup:
	temporal server start-dev --ui-port 8080

dev:
	@echo "Starting mock server, worker, and API server..."
	$(PYTHON) -m uvicorn mock_environment.main:app --port 9999 & \
	$(PYTHON) worker.py & \
	$(PYTHON) -m uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload & \
	wait

mock:
	$(PYTHON) -m uvicorn mock_environment.main:app --port 9999

worker:
	$(PYTHON) worker.py

api:
	$(PYTHON) -m uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload

start:
	$(PYTHON) main.py start workflow_definitions/e2e_test.json

transition:
	@test -n "$(WF_ID)" || (echo "Usage: make transition WF_ID=<id> T_ID=<id>" && exit 1)
	@test -n "$(T_ID)" || (echo "Usage: make transition WF_ID=<id> T_ID=<id>" && exit 1)
	$(PYTHON) main.py transition $(WF_ID) $(T_ID)

state:
	@test -n "$(WF_ID)" || (echo "Usage: make state WF_ID=<id>" && exit 1)
	$(PYTHON) main.py state $(WF_ID)

transitions:
	@test -n "$(WF_ID)" || (echo "Usage: make transitions WF_ID=<id>" && exit 1)
	$(PYTHON) main.py transitions $(WF_ID)

audit:
	@test -n "$(WF_ID)" || (echo "Usage: make audit WF_ID=<id>" && exit 1)
	$(PYTHON) main.py audit $(WF_ID)
