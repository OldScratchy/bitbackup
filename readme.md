# BitBackup!  🚀

A Python-based tool for backing up Bitbucket repositories to Azure Blob Storage.

## Description
BitBackup automates the process of backing up Bitbucket repositories and storing them securely in Azure Blob Storage. It supports multi-threading and includes Discord notifications for backup status. Also included a couple of tables for MSSQL backups, which can be used to monitor the backup status, and a Grafana dashboard (json) for visualizing the data.

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
THREAD_POOL_SIZE=<int>                   # Number of concurrent backup threads
CLIENT_ID=<Client-Id>                    # Client Id for BitBucket
CLIENT_SECRET=<Client-Secret>            # Client Secret for BitBucket
WORKSPACE=<Workspace>                    # BitBucket workspace
CONTAINER_NAME=<Container-Name>          # Container name (Azure Storage)
AZURE_STORAGE_ACCOUNT=<Storage-Account>  # Storage Account name
AZURE_STORAGE_KEY=<Storage-Key>          # Storage Account access key
DISCORD_WEBHOOK_URL=<Webhook-URL>        # Discord Webhook
AUTOEXECUTE=<bool>                       # Set 'true' to execute on init
MSSQL_SERVER=<Server-Name>               # MSSQL hostname
MSSQL_DATABASE=<Database-Name>           # DB name
MSSQL_USERNAME=<Username>                # DB username (db_owner on 1st run)
MSSQL_PASSWORD=<Password>
```

## Using Docker

1. Clone this repository
2. Ensure you have an SSH config file for Bitbucket. This should be placed in the root of the repository and named `config`. For example:

```bash
Host bitbucket.org
  AddKeysToAgent yes
  IdentityFile ~/.ssh/bitbucketcrt
```

3. Build the Docker image:

```bash
docker build -t bitbackup .
```

4. Run the container with the necessary environment variables:

```bash
docker run -d \
  -e THREAD_POOL_SIZE=<int> \
  -e CLIENT_ID=<Client-Id> \
  -e CLIENT_SECRET=<Client-Secret> \
  -e WORKSPACE=<Workspace> \
  -e CONTAINER_NAME=<Container-Name> \
  -e AZURE_STORAGE_ACCOUNT=<Storage-Account> \
  -e AZURE_STORAGE_KEY=<Storage-Key> \
  -e DISCORD_WEBHOOK_URL=<Webhook-URL> \
  -e AUTOEXECUTE=<bool> \
  -e MSSQL_SERVER=<Server-Name> \
  -e MSSQL_DATABASE=<Database-Name> \
  -e MSSQL_USERNAME=<Username> \
  -e MSSQL_PASSWORD=<Password> \
  -v /path/to/ssh/config:/home/backupuser/.ssh/config \
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

---

Feel free to reach out if you have any questions. Happy coding! 🚀