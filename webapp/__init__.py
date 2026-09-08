from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from flask import Flask, jsonify, send_from_directory

from .api.assets import audio_bp, bp as assets_bp
from .api.jobs import bp as jobs_bp
from .api.outputs import bp as outputs_bp
from .api.scripts import bp as scripts_bp
from .api.voice import bp as voice_bp

DIST = ROOT / "frontend" / "dist"


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200MB uploads

    app.register_blueprint(scripts_bp)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(assets_bp)
    app.register_blueprint(voice_bp)
    app.register_blueprint(outputs_bp)
    app.register_blueprint(audio_bp)

    @app.errorhandler(404)
    def not_found(e):
        from flask import request

        if request.path.startswith(("/api/", "/audio/")):
            return jsonify({"error": "not found"}), 404
        return _spa(request.path)

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": str(e)}), 500

    if DIST.exists():
        @app.route("/")
        def index():
            return send_from_directory(DIST, "index.html")

        @app.route("/<path:sub>")
        def spa_static(sub: str):
            if sub.startswith(("api/", "audio/")):
                from flask import abort

                abort(404)
            return _spa(sub)

    else:
        @app.route("/")
        def index():
            return jsonify(
                {
                    "app": "podcast-pipeline web",
                    "hint": "frontend not built; run `cd frontend && npm run build`, or use the Vite dev server",
                }
            )

    def _spa(path: str):
        target = (DIST / path).resolve()
        if target.is_file() and DIST.resolve() in target.parents:
            return send_from_directory(DIST, path)
        return send_from_directory(DIST, "index.html")

    return app
