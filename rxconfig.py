import os

import reflex as rx

# api_url is compiled INTO the frontend bundle. Change it -> `reflex run` must
# recompile. Restart the backend tunnel -> new random URL -> recompile.
# Symptom of getting this wrong: a page that renders perfectly and does nothing.
API_URL = os.environ.get("CONCIERGE_API_URL", "http://localhost:8000")

config = rx.Config(
    app_name="concierge",
    # Reflex resolves the app module as app_name + "." + app_name unless this is
    # set. Our app lives at concierge/app.py, so it must be "concierge.app".
    app_module_import="concierge.app",
    api_url=API_URL,
    # Pin the ports, or Reflex's "next available port" behaviour silently moves
    # the frontend and desyncs the tunnel.
    frontend_port=3000,
    backend_port=8000,
    # Defaults to False = localhost only, which makes a quick-tunnel URL return
    # "403 Blocked request. This host is not allowed." THIS IS THE DEMO-KILLER.
    vite_allowed_hosts=True,
)
