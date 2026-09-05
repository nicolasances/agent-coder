# One image per harness. Same contract, different adapter + CLI.
FROM node:22-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates curl python3 python3-pip ripgrep \
    && rm -rf /var/lib/apt/lists/*

# gcloud CLI, for object-store I/O only.
#RUN curl -sSL https://sdk.cloud.google.com | bash -s -- --disable-prompts --install-dir=/opt \
#    && ln -s /opt/google-cloud-sdk/bin/gcloud /usr/local/bin/gcloud

# GitHub CLI — needed for `gh pr create` (docs/concept.md §3.1, §4.4). Standard
# apt install per https://github.com/cli/cli/blob/trunk/docs/install_linux.md;
# re-check that doc if this ever stops working, rather than assuming it's stale.
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code
RUN npm install -g skills

# Add coding skills. `npm install -g skills` puts a `skills` binary on PATH
# (bin/cli.mjs) — it's not an npm subcommand, so it must be invoked directly.
RUN skills add nicolasances/skills-coding -y

WORKDIR /app
COPY requirements.txt /app/requirements.txt
# Debian bookworm's system Python is externally-managed (PEP 668); this is
# a single-purpose container image, not a shared interpreter, so installing
# system-wide is fine.
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Non-root. The agent gets no more privilege than it needs.
RUN useradd -m -u 1001 agent \
    && mkdir -p /workspace /task /out \
    && chown -R agent:agent /workspace /task /out

COPY runner/ /app/runner/
# COPY schemas/ /app/schemas/

USER agent
ENV PYTHONUNBUFFERED=1 \
    HOME=/home/agent \
    GIT_TERMINAL_PROMPT=0

# No credentials in the image. ANTHROPIC_BASE_URL points at your gateway;
# the Claude OAuth token is fetched from GCP Secret Manager at startup
# (GCP_PID + secret "claude_token"), using the job's service account.
ENTRYPOINT ["python3", "-m", "runner.main"]