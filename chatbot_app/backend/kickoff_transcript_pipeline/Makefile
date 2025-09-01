SHELL := pwsh

.PHONY: help run smoke test docker-build docker-test

help:
	@echo "make run          # run pipeline with defaults"
	@echo "make smoke        # run pytest quick"
	@echo "make docker-build # build container"
	@echo "make docker-test  # run tests in container"

run:
	python run_fusion.py --config configs/default.yaml

smoke:
	python -m pytest -q

docker-build:
	docker build -t transcript-pipeline:latest .

docker-test:
	docker run --rm -v ${PWD}:/app transcript-pipeline:latest python -m pytest -q
