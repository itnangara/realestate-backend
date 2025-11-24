# Makefile for common development tasks

.PHONY: validate-docs test seed-db help

validate-docs:
	@echo "Validating API documentation..."
	@python scripts/validate_api_docs.py

test:
	@pytest tests/ -v

seed-db:
	@python seed_database.py

help:
	@echo "Available commands:"
	@echo "  make validate-docs  - Validate API documentation against code"
	@echo "  make test          - Run tests"
	@echo "  make seed-db       - Seed database with initial data"

