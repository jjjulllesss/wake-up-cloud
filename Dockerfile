FROM python:3.9-slim

# Install required packages
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN useradd -m -s /bin/bash nodegroup

# Set working directory
WORKDIR /app

# Copy only the necessary files
COPY manage_node_groups.py .
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set the entrypoint
ENTRYPOINT ["python", "manage_node_groups.py"] 