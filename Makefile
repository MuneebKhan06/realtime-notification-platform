.PHONY: install test test-unit test-integration coverage lint format typecheck check up down migrate

install:
	pip install -r requirements-dev.txt

test-unit:
	pytest tests/ -v -m "not integration"

coverage:
	pytest tests/ -m "not integration" --cov=app --cov-report=term-missing --cov-report=html

test-integration:
	docker-compose -f docker-compose.test.yml up -d --build
	pytest tests/test_integration.py -m integration
	docker-compose -f docker-compose.test.yml down -v

test: test-unit

lint:
	ruff check app/ tests/ scripts/ load_tests/

format:
	ruff format app/ tests/ scripts/ load_tests/

typecheck:
	mypy app/

check: lint typecheck test-unit

up:
	docker-compose up -d

down:
	docker-compose down -v

migrate:
	alembic upgrade head
