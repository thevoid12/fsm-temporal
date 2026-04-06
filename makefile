PYTHON = env/bin/python

.PHONY: dev-setup dev mock worker start transition state transitions audit

dev-setup:
	temporal server start-dev --ui-port 8080

dev:
	@echo "Starting mock server and worker..."
	$(PYTHON) -m uvicorn mock_environment.main:app --port 9999 & \
	$(PYTHON) worker.py & \
	wait

mock:
	$(PYTHON) -m uvicorn mock_environment.main:app --port 9999

worker:
	$(PYTHON) worker.py

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
