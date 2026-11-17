import hashlib
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


def accent_hue(pr_number):
    """Golden-angle steps keep consecutive PRs far apart on the colour wheel,
    so side-by-side previews are easy to tell apart."""
    if not pr_number.isdigit():
        return 262
    return round(int(pr_number) * 137.508) % 360


def fingerprint(commit_sha):
    """20 bar hues derived from the commit, so every push looks different."""
    digest = hashlib.sha1(commit_sha.encode()).hexdigest()
    return [int(digest[i:i + 2], 16) * 360 // 256 for i in range(0, 40, 2)]


@app.route('/')
def home():
    info = build_info()
    bars = fingerprint(info['commit_sha'])
    return render_template(
        'index.html', info=info, hue=accent_hue(info['pr_number']), bars=bars,
        from_ci=bool(info['pr_number'] and info['commit_sha']),
    )


@app.route('/api/info')
def api_info():
    return jsonify(build_info())


if __name__ == '__main__':
    # Uses platform-provided port where applicable, defaults to 8080
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
