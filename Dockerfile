FROM python:3.13-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy project files
COPY pyproject.toml uv.lock* README.md ./
COPY src/ ./src/
COPY static/ ./static/

# Install dependencies
RUN uv sync --frozen --no-dev

# Create data directory for SQLite
RUN mkdir -p /app/data

EXPOSE 8080

# Run the application
CMD ["uv", "run", "obs-harness", "--host", "0.0.0.0", "--port", "8080", "--db", "sqlite+aiosqlite:///data/obs_harness.db"]
