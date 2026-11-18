# Use a small, production-appropriate base image
FROM python:3.11-slim@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Build metadata passed by CI (ci.yml build-args); app.py shows it on the page.
# Declared last so each new commit only invalidates these metadata-only layers.
ARG PR_NUMBER=
ARG COMMIT_SHA=
ARG BRANCH=
ARG BUILD_TIME=
ARG RUN_URL=
ARG REPO_URL=
ARG IMAGE_TAG=
ENV PR_NUMBER=$PR_NUMBER \
    COMMIT_SHA=$COMMIT_SHA \
    BRANCH=$BRANCH \
    BUILD_TIME=$BUILD_TIME \
    RUN_URL=$RUN_URL \
    REPO_URL=$REPO_URL \
    IMAGE_TAG=$IMAGE_TAG

# Set environment port and expose it
ENV PORT=8080
EXPOSE $PORT

# Start command binding to 0.0.0.0 and the configured port.
# --preload imports the app once, so every worker reports the same start time.
CMD gunicorn --preload --bind 0.0.0.0:$PORT app:app
