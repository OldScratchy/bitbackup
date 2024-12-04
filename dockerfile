FROM python:3.13.0-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN useradd -m backupuser

WORKDIR /bitbackup

COPY bitbackup.py .
RUN chown -R backupuser /bitbackup

RUN apt-get update --no-cache && \
    apt-get install -y --no-install-recommends \
        software-properties-common \
        wget \
        gnupg \
        ca-certificates \
        git \
        openssh-client \
        build-essential \
        libssl-dev \
        zlib1g-dev \
        libbz2-dev \
        libreadline-dev \
        libsqlite3-dev \
        libffi-dev \
        libncursesw5-dev \
        xz-utils \
        tk-dev \
        libxml2-dev \
        libxmlsec1-dev \
        liblzma-dev \
        apt-transport-https \
        unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /etc/apt/keyrings

RUN wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /etc/apt/keyrings/microsoft.gpg && \
    echo "deb [arch=amd64,arm64,armhf signed-by=/etc/apt/keyrings/microsoft.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" | tee /etc/apt/sources.list.d/microsoft-prod.list

RUN apt-get update

RUN wget https://www.openssl.org/source/openssl-1.1.1p.tar.gz -O openssl-1.1.1p.tar.gz && \
tar -zxvf openssl-1.1.1p.tar.gz && \
cd openssl-1.1.1p && \
./config && \
make && \
make install && \
ldconfig

RUN ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
        msodbcsql18 \
        mssql-tools \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="$PATH:/opt/mssql-tools/bin"

RUN pip install --no-cache-dir \
    setuptools \
    requests \
    azure-storage-blob \
    pyfiglet \
    schedule \
    tenacity \
    tabulate \
    discord-webhook \
    pyodbc \
    colorama

RUN mkdir -p /home/backupuser/.ssh

COPY bitbucketcrt /home/backupuser/.ssh/bitbucketcrt
COPY bitbucketcrt.pub /home/backupuser/.ssh/bitbucketcrt.pub

COPY config /home/backupuser/.ssh/config

RUN ssh-keyscan bitbucket.org >> /home/backupuser/.ssh/known_hosts

RUN chown -R backupuser:backupuser /home/backupuser/.ssh /bitbackup

RUN chmod 700 /home/backupuser/.ssh && \
    chmod 600 /home/backupuser/.ssh/bitbucketcrt && \
    chmod 644 /home/backupuser/.ssh/bitbucketcrt.pub

USER backupuser

# ENV CLIENT_ID               =   <Client-Id>
# ENV CLIENT_SECRET           =   <Client-Secret>

# ENV WORKSPACE               =   <Workspace>

# ENV CONTAINER_NAME          =   <Container-Name>
# ENV AZURE_STORAGE_ACCOUNT   =   <Storage-Account>
# ENV AZURE_STORAGE_KEY       =   <Storage-Key>

# ENV DISCORD_WEBHOOK_URL     =   <Webhook-URL>

# ENV AUTOEXECUTE           =   true

# ENV MSSQL_SERVER            =   <Server-Name>
# ENV MSSQL_DATABASE          =   <Database-Name>
# ENV MSSQL_USERNAME          =   <Username>
# ENV MSSQL_PASSWORD          =   <Password>

CMD ["python", "bitbackup.py"]