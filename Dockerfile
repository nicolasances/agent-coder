# One image per harness. Same contract, different adapter + CLI.
FROM node:22-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates curl python3 python3-pip python3-venv ripgrep \
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

# Non-root. The agent gets no more privilege than it needs. The runner's
# startup skills install runs as this user, so it lands in its home — not root's.
RUN useradd -m -u 1001 agent \
    && mkdir -p /workspace /task /out \
    && chown -R agent:agent /workspace /task /out

USER agent
ENV HOME=/home/agent

# Skills are NOT installed here. The runner installs the latest
# nicolasances/skills-coding at every container start (runner/skills.py), so a
# change to the skills repo reaches the next run without an image rebuild. A
# build-time install was also a cached layer that went stale on rebuilds.
# Only the `skills` CLI itself is baked in, above.

# A venv, not the system Python: agent owns it outright, so installing into
# it needs no root and no --break-system-packages workaround for Debian's
# PEP 668 restriction — that restriction only applies to the system-managed
# interpreter, which this deliberately isn't.
RUN python3 -m venv /home/agent/venv

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN /home/agent/venv/bin/pip install --no-cache-dir -r requirements.txt

COPY runner/ /app/runner/
# COPY schemas/ /app/schemas/

ENV PYTHONUNBUFFERED=1 \
    GIT_TERMINAL_PROMPT=0

# No credentials in the image. ANTHROPIC_BASE_URL points at your gateway;
# the Claude OAuth token is fetched from GCP Secret Manager at startup
# (GCP_PID + secret "claude_token"), using the job's service account.
#
# Runs as `agent` throughout — set once, above, and never switched back to
# root. The venv's own python3 is used here specifically (not the bare
# `python3` on PATH), since that's where requirements.txt actually got
# installed.
ENTRYPOINT ["/home/agent/venv/bin/python3", "-m", "runner.main"]