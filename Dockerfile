# Use Python 3.10 slim version as the base image
FROM python:3.10-slim

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies
# - ffmpeg: Required by many audio processing libraries, including TTS/pydub
# - git: Sometimes needed by pip to install packages directly from repositories (or by TTS itself)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file first to leverage Docker cache
COPY requirements.txt .

# Upgrade pip and install Python dependencies
# Using --no-cache-dir can reduce image size slightly but might slow down builds
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# --- ADD THIS LINE ---
# Set environment variable to automatically agree to Coqui TTS Terms of Service
# This prevents the interactive prompt that causes EOFError in Docker
ENV COQUI_TOS_AGREED=1
# ---------------------

# Copy the rest of the application code into the container
COPY . .

# Expose the port the application will run on (inside the container)
# Runpod will map this to an external port.
EXPOSE 8000

# Command to run the application using uvicorn
# --host 0.0.0.0 makes the server accessible from outside the container
# --port 8000 matches the EXPOSE instruction
# --workers 1 (default) is often fine for GPU tasks, adjust if needed
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# --- Notes for Runpod Deployment ---
# 1. Ensure you select a GPU instance on Runpod as main.py uses gpu=True.
# 2. The TTS model files will be downloaded when the container starts for the first time. 
#    This can take several minutes depending on the network speed and model size.
# 3. Runpod will handle mapping the internal port 8000 to a public URL.
# 4. Consider mounting a persistent volume to /app/voices and /app/cloned if you 
#    need the uploaded samples and generated audio to persist across pod restarts.