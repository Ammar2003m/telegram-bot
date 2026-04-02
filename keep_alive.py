import os
import logging
from flask import Flask
from threading import Thread

log = logging.getLogger(__name__)

app = Flask("")


@app.route("/")
def home():
    return "✅ متجر روز Bot is alive!"


@app.route("/health")
def health():
    return {"status": "ok", "bot": "StoreRozbot"}, 200


def _run():
    port = int(os.getenv("PORT", 8080))
    for try_port in [port, port + 1, port + 2, 8888, 9000]:
        try:
            app.run(host="0.0.0.0", port=try_port,
                    use_reloader=False, use_debugger=False)
            break
        except OSError:
            log.warning(f"Port {try_port} busy, trying next…")
    else:
        log.error("No available port for Flask keep-alive server.")


def keep_alive():
    t = Thread(target=_run, daemon=True)
    t.start()
