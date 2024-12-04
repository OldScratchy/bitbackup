# BitBackup

A Python-based tool for backing up Bitbucket repositories to Azure Blob Storage.

## Description
BitBackup automates the process of backing up Bitbucket repositories and storing them securely in Azure Blob Storage. It supports multi-threading and includes Discord notifications for backup status.

## Prerequisites

### Azure Requirements
- Azure Storage Account
- Storage Account Connection String
- Container name for backups

### Bitbucket Requirements
- SSH key pair configured in Bitbucket
- Bitbucket workspace access
- Repository read access

### Discord (Optional)
- Discord webhook URL for notifications

## Environment Variables

```bash
THREAD_POOL_SIZE=1                    # Number of concurrent backup threads
AZURE_STORAGE_CONNECTION_STRING=      # Azure Storage connection string
AZURE_CONTAINER_NAME=                 # Azure Storage container name
BITBUCKET_SSH_KEY_PATH=              # Path to Bitbucket SSH private key
DISCORD_WEBHOOK_URL=                  # Discord webhook URL (optional)
```

## Using Docker

1. Clone this repository
2. Build the Docker image:

```bash
docker build -t bitbackup .
```

3. Run the container:

```bash
docker run -d \
  -e AZURE_STORAGE_CONNECTION_STRING="your_connection_string" \
  -e AZURE_CONTAINER_NAME="your_container" \
  -e BITBUCKET_SSH_KEY_PATH="/path/to/key" \
  -v /path/to/ssh/key:/path/to/key \
  bitbackup
```

## Features
- Multi-threaded repository backup
- Azure Blob Storage integration
- Discord notifications
- Retry mechanism for failed operations
- Logging and monitoring
- Scheduled backups

## Security Notes
- Store SSH keys securely
- Use environment variables for sensitive data
- Run container as non-root user
- Keep Python packages updated

## Dependencies
- Python 3.13
- OpenSSL 1.1.1p
- Git
- Required Python packages listed in Dockerfile 🤗

Add:

Host bitbucket.org
  AddKeysToAgent yes
  IdentityFile ~/.ssh/bitbucketcrt