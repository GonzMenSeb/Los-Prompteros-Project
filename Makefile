PY := PYTHONPATH=. ./.venv/bin/python
.PHONY: setup dev tunnel check verify fixtures doctor clean

setup:
	python3.12 -m venv .venv
	./.venv/bin/pip install -q --upgrade pip
	./.venv/bin/pip install -q -r requirements.txt
	@test -f .env || cp .env.example .env
	@mkdir -p bin
	@test -f bin/cloudflared || (curl -sL -o bin/cloudflared \
	  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
	  && chmod +x bin/cloudflared)
	@echo "setup ok — paste your key into .env"

dev:
	./.venv/bin/reflex run

tunnel:
	@bash scripts/tunnel.sh

check:
	$(PY) -m pytest -m "not live" -q

verify:
	$(PY) -m pytest -m live -q

fixtures:
	$(PY) scripts/dump_fixtures.py

doctor:
	@$(PY) scripts/doctor.py

clean:
	rm -rf .web .tunnel __pycache__ .pytest_cache
