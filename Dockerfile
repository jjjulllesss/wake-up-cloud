# Build stage for AWS CLI
FROM python:3.9-slim as aws-cli
RUN apt-get update && apt-get install -y \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*
RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-$(uname -m).zip" -o "awscliv2.zip" \
    && unzip awscliv2.zip \
    && ./aws/install \
    && rm -rf awscliv2.zip aws

# Build stage for GCP SDK
FROM python:3.9-slim as gcp-sdk
RUN apt-get update && apt-get install -y \
    curl \
    apt-transport-https \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list \
    && curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key --keyring /usr/share/keyrings/cloud.google.gpg add - \
    && apt-get update && apt-get install -y google-cloud-sdk \
    && rm -rf /var/lib/apt/lists/*

# Final stage
FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Copy AWS CLI from build stage
COPY --from=aws-cli /usr/local/aws-cli /usr/local/aws-cli
COPY --from=aws-cli /usr/local/bin/aws /usr/local/bin/aws

# Copy GCP SDK from build stage
COPY --from=gcp-sdk /usr/lib/google-cloud-sdk /usr/lib/google-cloud-sdk
COPY --from=gcp-sdk /usr/bin/gcloud /usr/bin/gcloud
COPY --from=gcp-sdk /usr/bin/gsutil /usr/bin/gsutil

# Set up Python environment
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY manage_node_groups.py .
COPY run.sh .
COPY run-container.sh .

# Set up non-root user
RUN useradd -m -u 1000 appuser && \
    mkdir -p /home/appuser/.aws /home/appuser/.config/gcloud && \
    chown -R appuser:appuser /home/appuser /app

# Set up environment
ENV PATH="/usr/local/aws-cli/v2/current/bin:${PATH}"
ENV PYTHONUNBUFFERED=1

# Switch to non-root user
USER appuser

# Set entrypoint
ENTRYPOINT ["./run.sh"] 