# One image per harness. Same contract, different adapter + CLI.
FROM node:22-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates curl python3 python3-pip ripgrep \
    && rm -rf /var/lib/apt/lists/*

# gcloud CLI, for object-store I/O only. 
RUN curl -sSL https://sdk.cloud.google.com | bash -s -- --disable-prompts --install-dir=/opt \
    && ln -s /opt/google-cloud-sdk/bin/gcloud /usr/local/bin/gcloud

RUN npm install -g @anthropic-ai/claude-code

# Non-root. The agent gets no more privilege than it needs.
RUN useradd -m -u 1001 agent \
    && mkdir -p /workspace /task /out \
    && chown -R agent:agent /workspace /task /out

WORKDIR /app
COPY runner/ /app/runner/
COPY schemas/ /app/schemas/

USER agent
ENV PYTHONUNBUFFERED=1 \
    HOME=/home/agent \
    GIT_TERMINAL_PROMPT=0

# No credentials in the image. ANTHROPIC_BASE_URL points at your gateway;
# tokens arrive as env at execution time from Secret Manager.
ENTRYPOINT ["python3", "-m", "runner.main"]