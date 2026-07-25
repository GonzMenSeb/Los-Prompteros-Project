PY := PYTHONPATH=. ./.venv/bin/python
PHASE ?= prewarm
.PHONY: setup dev walkthrough rehearse tunnel check verify fixtures doctor clean

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

# The watchable demo: clean server, browser opened, script already running.
#   make walkthrough                 refusal + research + real kit   ~3 min
#   make walkthrough PHASE=onstage   injection blocked + real cart   ~25 s
#   make walkthrough PHASE=all       end to end, for rehearsal
walkthrough:
	@bash scripts/walkthrough.sh $(PHASE)

# Same script, no browser: asserts every beat and prints the wall clock per phase.
rehearse:
	$(PY) scripts/verify_walkthrough.py

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
