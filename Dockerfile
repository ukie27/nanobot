FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Install Node.js 20 for the WhatsApp bridge
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates gnupg git openssh-client && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" > /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get purge -y gnupg && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install locked Python dependencies first (cached layer).
COPY pyproject.toml uv.lock README.md LICENSE THIRD_PARTY_NOTICES.md ./
RUN uv export --frozen --no-dev --no-emit-project --output-file /tmp/requirements.txt && \
    uv pip install --system --no-cache -r /tmp/requirements.txt

# Copy the full source and install
COPY career_console/ career_console/
COPY integrations/whatsapp-bridge/ integrations/whatsapp-bridge/
COPY migrations/ migrations/
COPY alembic.ini ./
RUN uv pip install --system --no-cache --no-deps .

# Build the WhatsApp bridge
RUN git config --global url."https://github.com/".insteadOf "ssh://git@github.com/"

WORKDIR /app/integrations/whatsapp-bridge
RUN npm ci && npm run build
WORKDIR /app

# Create config directory
RUN mkdir -p /data/CareerConsole

# CareerConsole Web/API port
EXPOSE 8765

ENTRYPOINT ["career-console"]
CMD ["serve", "--workspace", "/data/CareerConsole", "--host", "0.0.0.0", "--port", "8765"]
