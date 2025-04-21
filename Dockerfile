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
COPY run.sh .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Make run.sh executable
RUN chmod +x run.sh

# Set the command
CMD ["./run.sh"] 