.PHONY: install run-backend run-frontend run

install:
	pip install -r requirements.txt
	cd frontend && npm install

run-backend:
	uvicorn backend.main:app --reload --port 8000

run-frontend:
	cd frontend && npm run dev

run:
	@echo "Starting backend and frontend..."
	@start /B uvicorn backend.main:app --reload --port 8000
	@cd frontend && npm run dev
