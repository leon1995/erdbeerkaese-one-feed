# Use the official uv Debian image as base
FROM ghcr.io/astral-sh/uv:debian

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml uv.lock .python-version ./
COPY app.py app.py

# Install dependencies
RUN uv sync --frozen

# Expose port 8000 (default uvicorn port)
EXPOSE 8000

# Set environment variables
ENV UV_SYSTEM_PYTHON=1

# Run the FastAPI application with uvicorn
CMD ["uv", "run", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
