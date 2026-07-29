"""Preflight. Run this at 08:05 when four laptops need the same green state fast."""

import pathlib
import shutil
import subprocess
import sys

import httpx

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ok = True


def check(label: str, passed: bool, detail: str = "") -> None:
    global ok
    ok &= passed
    print(f"{'PASS' if passed else 'FAIL'}  {label}{'  — ' + detail if detail else ''}")


check("python >= 3.11", sys.version_info >= (3, 11), sys.version.split()[0])
check("cloudflared present", any((ROOT / "bin" / n).exists() for n in ("cloudflared", "cloudflared.exe")) or bool(shutil.which("cloudflared")))
check(".env present", (ROOT / ".env").exists())
check(".env gitignored", ".env" in (ROOT / ".gitignore").read_text())

def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True).stdout


check("no .env tracked", not git("ls-files", ".env").strip())

for mod, ver in [("reflex", "0.9.7"), ("google.genai", "2.14.0"), ("pydantic", None)]:
    try:
        m = __import__(mod, fromlist=["__version__"])
        got = getattr(m, "__version__", None) or getattr(m, "VERSION", "?")
        check(f"{mod} importable", True, str(got))
    except Exception as e:
        check(f"{mod} importable", False, str(e)[:80])

key = ""
for line in (ROOT / ".env").read_text().splitlines() if (ROOT / ".env").exists() else []:
    if line.startswith("GEMINI_API_KEY="):
        key = line.split("=", 1)[1].strip()
check("GEMINI_API_KEY set", bool(key) and key != "your-key-here")
if key:
    check("key value never committed", not git("log", "--all", "-S", key, "--oneline").strip())

if key:
    try:
        r = httpx.get("https://generativelanguage.googleapis.com/v1beta/models",
                      params={"key": key}, timeout=20)
        names = [m["name"] for m in r.json().get("models", [])]
        check("gemini-3.6-flash available", "models/gemini-3.6-flash" in names)
    except Exception as e:
        check("gemini reachable", False, str(e)[:80])

try:
    r = httpx.get("https://www.decathlon.com/collections.json?limit=250", timeout=30)
    check("storefront feed", r.status_code == 200, f"{len(r.json()['collections'])} collections")
except Exception as e:
    check("storefront feed", False, str(e)[:80])

try:
    from concierge.commerce.ucp import CONTEXT, EP, PROF

    r = httpx.post(EP, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                             "params": {"name": "search_catalog",
                                        "arguments": {"meta": {"ucp-agent": {"profile": PROF}},
                                                      "catalog": {"query": "tent", "context": CONTEXT,
                                                                  "pagination": {"limit": 1}}}}}, timeout=45)
    check("UCP MCP endpoint", r.status_code == 200 and "result" in r.json(),
          "429 = rate limited, ~48min — demo still works, paced" if r.status_code == 429 else str(r.status_code))
except Exception as e:
    check("UCP MCP endpoint", False, str(e)[:80])

print("\n" + ("ALL GREEN" if ok else "NOT READY — fix the FAILs above"))
sys.exit(0 if ok else 1)
