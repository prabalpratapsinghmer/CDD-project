import os
import socket
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template

app = Flask(__name__)

# Shared by all workers because the Dockerfile starts gunicorn --preload.
STARTED_AT = datetime.now(timezone.utc)


def build_info():
    """What CI baked into this image (Dockerfile ARG -> ENV).

    Empty values mean a local run that CI never built.
    """
    env = os.environ.get
    return {
        'pr_number': env('PR_NUMBER', ''),
        'commit_sha': env('COMMIT_SHA', ''),
        'branch': env('BRANCH', ''),
        'build_time': env('BUILD_TIME', ''),
        'run_url': env('RUN_URL', ''),
        'repo_url': env('REPO_URL', ''),
        'image_tag': env('IMAGE_TAG', ''),
        'hostname': socket.gethostname(),
        'started_at': STARTED_AT.isoformat(),
        'uptime_seconds': int(
            (datetime.now(timezone.utc) - STARTED_AT).total_seconds()),
    }


@app.route('/')
def home():
    info = build_info()
    return render_template('dashboard.html', info=info)


@app.route('/api/info')
def api_info():
    return jsonify(build_info())


if __name__ == '__main__':
    # Uses platform-provided port where applicable, defaults to 8080
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
