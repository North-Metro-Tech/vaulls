# Contributing to VAULLS

Thanks for your interest in contributing to VAULLS!

## Setup

```bash
git clone https://github.com/North-Metro-Tech/vaulls.git
cd vaulls
pip install -e ".[dev]"
```

## Running tests

```bash
pytest
```

All tests must pass before submitting a PR.

## PR expectations

- Tests must pass for all supported Python versions (3.10, 3.11, 3.12)
- Keep the API surface minimal — avoid adding new public exports unless necessary
- New features should include tests
- Follow the existing code style (run `ruff check .` to lint)

## License

This project is licensed under the MIT License. By contributing, you agree that your contributions will be licensed under the same terms.
