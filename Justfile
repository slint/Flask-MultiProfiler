set positional-arguments

test *args: install
  uv run pytest {{args}}

format *args:
  uvx ruff format {{args}}

lint *args:
  uvx ruff check --fix {{args}}

install:
  uv sync --all-extras
