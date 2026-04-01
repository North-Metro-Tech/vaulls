.PHONY: test lint build publish clean

test:
	pytest

lint:
	ruff check .

build:
	python -m build

publish:
	twine upload dist/*

clean:
	rm -rf dist/ build/ *.egg-info/
