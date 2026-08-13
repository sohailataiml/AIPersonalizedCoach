# Future Coach Intelligence Platform
#
#   make setup   install backend + frontend dependencies
#   make dev     run backend (8000) and frontend (3000) together
#   make test    backend test suite
#   make verify  everything a reviewer should see green
#
SHELL := /bin/bash
PY ?= python
BACKEND := backend
FRONTEND := frontend

.PHONY: help setup dev dev-backend dev-frontend seed test test-frontend lint typecheck build verify verify-ontology docker clean

help:
	@echo "make setup   - install dependencies (backend + frontend)"
	@echo "make dev     - run backend :8000 and frontend :3000"
	@echo "make seed    - seed/verify the knowledge graph from a clean state"
	@echo "make test    - backend tests"
	@echo "make verify  - tests + lint + typecheck + build + ontology audit + demo scenarios"
	@echo "make verify-ontology - re-resolve every SNOMED code at NCI EVS (network)"
	@echo "make docker  - full stack incl. Neo4j via docker compose"

setup:
	$(PY) -m pip install -e "$(BACKEND)[dev]"
	cd $(FRONTEND) && npm install

dev:
	@echo "backend  -> http://localhost:8000/docs"
	@echo "frontend -> http://localhost:3000"
	@trap 'kill 0' EXIT INT TERM; \
	( cd $(BACKEND) && $(PY) -m uvicorn app.main:app --reload --port 8000 ) & \
	( cd $(FRONTEND) && npm run dev ) & \
	wait

dev-backend:
	cd $(BACKEND) && $(PY) -m uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd $(FRONTEND) && npm run dev

seed:
	$(PY) scripts/seed_graph.py

test:
	cd $(BACKEND) && $(PY) -m pytest -q

test-frontend:
	cd $(FRONTEND) && npm test

# Re-resolves every SNOMED CT code against the NCI EVS terminology server.
# Kept out of `verify` on purpose: it needs the network, and a transport
# failure is not a mapping failure.
verify-ontology:
	$(PY) scripts/verify_ontology.py --live

lint:
	cd $(BACKEND) && $(PY) -m ruff check app tests
	cd $(FRONTEND) && npm run lint

typecheck:
	cd $(FRONTEND) && npm run typecheck

build:
	cd $(FRONTEND) && npm run build

verify: test lint typecheck build
	$(PY) scripts/seed_graph.py --dry-run
	$(PY) scripts/verify_ontology.py
	$(PY) scripts/demo_scenarios.py

docker:
	docker compose up --build

clean:
	rm -rf $(FRONTEND)/.next $(BACKEND)/.pytest_cache $(BACKEND)/.ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
