PY := PYTHONPATH=. ./.venv/bin/python
PHASE ?= prewarm
.PHONY: setup dev walkthrough rehearse tunnel reload check verify fixtures doctor clean distclean

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

# Pick up .env / code changes WITHOUT minting new tunnel URLs, so a QR code already
# in the wild stays valid. `make tunnel` would invalidate it.
reload:
	@bash scripts/reload.sh

check:
	$(PY) -m pytest -m "not live" -q

verify:
	$(PY) -m pytest -m live -q

fixtures:
	$(PY) scripts/dump_fixtures.py

doctor:
	@$(PY) scripts/doctor.py

# Run artifacts only. Leaves .web/ and bin/cloudflared alone — dropping those costs a
# long recompile and a 38 MB re-download, which is not what you want before a demo.
clean:
	rm -rf .tunnel .states .playwright-mcp .pytest_cache .reflex-*.log
	find . -path ./.venv -prune -o -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

# Everything clean does, plus the build caches. Next `make dev` recompiles from scratch.
distclean: clean
	rm -rf .web reflex.lock
