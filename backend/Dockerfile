FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set up user
RUN useradd -m -u 1000 user

# Create directories and set permissions
WORKDIR /app/legal_ai_platform/backend
RUN chown -R user:user /app

# Switch to non-root user
USER user

# Set PATH for user-installed pip packages
ENV PATH="/home/user/.local/bin:${PATH}"

# Copy requirements and install dependencies
COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# Copy backend source code
COPY --chown=user:user . .

# Expose port 7860 (Hugging Face Spaces requirement)
EXPOSE 7860

# Set environment variables for production/Hugging Face
ENV PORT=7860
ENV HOST=0.0.0.0

# Command to run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
