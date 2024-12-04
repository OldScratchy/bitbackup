import os
import logging
import requests
import subprocess
import shutil
import datetime
import tempfile
import pyfiglet
import schedule
import time
import pyodbc
import traceback
from azure.storage.blob import BlobServiceClient
from concurrent.futures import ThreadPoolExecutor, as_completed
from tenacity import retry, wait_fixed, stop_after_attempt, retry_if_exception_type, RetryError
from tabulate import tabulate
from discord_webhook import DiscordWebhook, DiscordEmbed
from colorama import Fore, Style

APP_NAME = "BitBackup!"
VERSION = "1.2411.1101"
DESCRIPTION = "Script para respaldar repositorios de Bitbucket y almacenarlos en Azure Blob Storage."

logger = logging.getLogger('BitBackup')
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)

# file_handler = logging.FileHandler('bitbackup.log')
# file_handler.setLevel(logging.DEBUG)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')
console_handler.setFormatter(formatter)
# file_handler.setFormatter(formatter)

logger.addHandler(console_handler)
# logger.addHandler(file_handler)

# Solo para logs de Azure
azure_logger = logging.getLogger('azure')
azure_logger.setLevel(logging.WARNING)

try:
    THREAD_POOL_SIZE = int(os.environ.get('THREAD_POOL_SIZE', '1'))
except ValueError:
    logger.warning("THREAD_POOL_SIZE debe ser un numero entero. Utilizando valor por defecto THREAD_POOL_SIZE = 1.")
    THREAD_POOL_SIZE = 1

if THREAD_POOL_SIZE <= 5 and THREAD_POOL_SIZE > 1:
    os.environ['AZURE_STORAGE_BLOB_MAX_CONCURRENCY'] = str(THREAD_POOL_SIZE)
else:
    logger.warning("El tamaño del pool de hilos para Azure Storage no puede ser mayor a 5. Cambiado a THREAD_POOL_SIZE = 5")
    THREAD_POOL_SIZE = 5
    os.environ['AZURE_STORAGE_BLOB_MAX_CONCURRENCY'] = str(THREAD_POOL_SIZE)

AUTOEXECUTE_STR = os.environ.get('AUTOEXECUTE', 'false').lower()
AUTOEXECUTE = AUTOEXECUTE_STR in ('true', '1', 't', 'yes', 'y')

MSSQL_SERVER = os.environ.get('MSSQL_SERVER')
MSSQL_DATABASE = os.environ.get('MSSQL_DATABASE')
MSSQL_USERNAME = os.environ.get('MSSQL_USERNAME')
MSSQL_PASSWORD = os.environ.get('MSSQL_PASSWORD')
MSSQL_DRIVER = os.environ.get('MSSQL_DRIVER', 'ODBC Driver 18 for SQL Server')

def validate_config():
    required_vars = [
        'CLIENT_ID', 'CLIENT_SECRET', 'WORKSPACE',
        'AZURE_STORAGE_ACCOUNT', 'AZURE_STORAGE_KEY', 'CONTAINER_NAME',
        'DISCORD_WEBHOOK_URL',
        'MSSQL_SERVER', 'MSSQL_DATABASE', 'MSSQL_USERNAME', 'MSSQL_PASSWORD'
    ]
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    if missing_vars:
        logger.error(f"Faltan las siguientes variables de entorno: {', '.join(missing_vars)}")
        return False
    return True

def get_mssql_connection():
    try:
        conn_str = f'DRIVER={{{MSSQL_DRIVER}}};SERVER={MSSQL_SERVER};DATABASE={MSSQL_DATABASE};UID={MSSQL_USERNAME};PWD={MSSQL_PASSWORD}'
        conn = pyodbc.connect(conn_str)
        return conn
    except Exception as e:
        logger.error(f"Error al conectar a MSSQL: {e}")
        return None

def create_tables(conn):
    try:
        cursor = conn.cursor()
        cursor.execute('''
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='BackupTasks' AND xtype='U')
            CREATE TABLE BackupTasks (
                TaskID INT IDENTITY(1,1) PRIMARY KEY,
                StartTime DATETIME,
                EndTime DATETIME,
                TotalRepos INT,
                SuccessfulBackups INT,
                FailedBackups INT
            )
        ''')
        cursor.execute('''
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='RepositoryBackups' AND xtype='U')
            CREATE TABLE RepositoryBackups (
                RepoID INT IDENTITY(1,1) PRIMARY KEY,
                TaskID INT FOREIGN KEY REFERENCES BackupTasks(TaskID),
                RepoName VARCHAR(255),
                RepoURL VARCHAR(500),
                Status VARCHAR(50),
                Duration FLOAT,
                ErrorMessage VARCHAR(MAX)
            )
        ''')
        conn.commit()
    except Exception as e:
        logger.error(f"Error al crear las tablas en MSSQL: {e}")

def perform_backup():
    start_time = datetime.datetime.now()
    if not validate_config():
        return

    BITBUCKET_CLIENT_ID = os.environ.get('CLIENT_ID')
    BITBUCKET_CLIENT_SECRET = os.environ.get('CLIENT_SECRET')
    BITBUCKET_WORKSPACE = os.environ.get('WORKSPACE')

    AZURE_STORAGE_ACCOUNT = os.environ.get('AZURE_STORAGE_ACCOUNT')
    AZURE_STORAGE_KEY = os.environ.get('AZURE_STORAGE_KEY')
    CONTAINER_NAME = os.environ.get('CONTAINER_NAME')

    DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')

    CURRENT_DATE = datetime.datetime.now()
    YEAR = CURRENT_DATE.strftime("%Y")
    MONTH = CURRENT_DATE.strftime("%m")
    DAY = CURRENT_DATE.strftime("%d")
    DATE_STR = CURRENT_DATE.strftime("%Y-%m-%d")
    TIME_STR = CURRENT_DATE.strftime("%H-%M-%S")

    conn = get_mssql_connection()
    if not conn:
        logger.error("No se pudo establecer conexión con MSSQL.")
        return

    create_tables(conn)
    
    @retry(wait=wait_fixed(5), stop=stop_after_attempt(3))
    def get_bitbucket_token():
        auth_response = requests.post(
            "https://bitbucket.org/site/oauth2/access_token",
            auth=(BITBUCKET_CLIENT_ID, BITBUCKET_CLIENT_SECRET),
            data={'grant_type': 'client_credentials'}
        )
        auth_response.raise_for_status()
        return auth_response.json().get('access_token')

    try:
        access_token = get_bitbucket_token()
    except Exception as e:
        logger.error(f"Error al obtener el token de acceso de Bitbucket: {e}")
        return
    
    headers = {'Authorization': f'Bearer {access_token}'}
    repo_url = f"https://api.bitbucket.org/2.0/repositories/{BITBUCKET_WORKSPACE}?pagelen=100"
    repo_list = []
    
    logger.info("Obteniendo lista de repositorios...")
    while repo_url:
        try:
            response = requests.get(repo_url, headers=headers)
            response.raise_for_status()
            data = response.json()
            for repo in data.get('values', []):
                clone_links = repo.get('links', {}).get('clone', [])
                ssh_link = next((link.get('href') for link in clone_links if link.get('name') == 'ssh'), None)
                if ssh_link:
                    repo_list.append(ssh_link)
            repo_url = data.get('next')
        except Exception as e:
            logger.error(f"Error al obtener la lista de repositorios: {e}")
            return

    total_repos = len(repo_list)
    successful_backups = 0
    failed_backups = 0
    
    logger.info(f"Cantidad de repositorios: {total_repos}")
    logger.info(f"Fecha: {DATE_STR}")
    logger.info(f"Hora: {TIME_STR}")

    successful_backups = 0
    failed_backups = 0

    TMP_DIR = tempfile.mkdtemp(prefix="bitbackup_")

    repo_results = []
    
    def process_repository(repo_url):
        nonlocal successful_backups, failed_backups
        repo_name = os.path.basename(repo_url).replace('.git', '')
        repo_dir = os.path.join(TMP_DIR, repo_name)
        zip_name = f"{repo_name}_{DATE_STR}_{TIME_STR}.zip"
        zip_path = os.path.join(TMP_DIR, zip_name)
        blob_name = f"{YEAR}/{MONTH}/{DAY}/{zip_name}"
        start_repo_time = datetime.datetime.now()
        status = 'Failed'
        error_message = ''
        try:
            @retry(wait=wait_fixed(5), stop=stop_after_attempt(3), retry=(retry_if_exception_type(Exception)), reraise=True)
            def clone_repo():
                logger.info(f"Clonando {repo_url}...")
                clone_result = subprocess.run(
                    ['git', 'clone', '--mirror', repo_url, repo_dir],
                    capture_output=True, text=True
                )
                if clone_result.returncode != 0:
                    logger.error(f"Error al clonar {repo_url}")
                    logger.error(f"STDOUT: {clone_result.stdout}")
                    logger.error(f"STDERR: {clone_result.stderr}")
                    raise Exception(f"Error al clonar {repo_url}: {clone_result.stderr}")

            @retry(wait=wait_fixed(5), stop=stop_after_attempt(3), retry=(retry_if_exception_type(Exception)), reraise=True)
            def upload_zip():
                logger.info(f"Subiendo {zip_name} a Azure Storage...")
                blob_service_client = BlobServiceClient(
                    f"https://{AZURE_STORAGE_ACCOUNT}.blob.core.windows.net",
                    credential=AZURE_STORAGE_KEY
                )
                blob_client = blob_service_client.get_blob_client(container=CONTAINER_NAME, blob=blob_name)
                with open(zip_path, "rb") as data:
                    blob_client.upload_blob(data, overwrite=True)

            clone_repo()
            logger.info(f"Comprimiendo {repo_name}...")
            shutil.make_archive(zip_path.replace('.zip', ''), 'zip', repo_dir)
            upload_zip()
            status = 'Success'
            successful_backups += 1
            logger.info(f"Repositorio {repo_name} procesado exitosamente.")
        except RetryError as re:
            original_exception = re.last_attempt.exception()
            error_message = str(original_exception)
            logger.error(f"Error al procesar {repo_url} después de varios reintentos.")
            logger.error(f"Excepción original: {original_exception}")
            logger.error(traceback.format_exc())
            failed_backups += 1
        except Exception as e:
            error_message = str(e)
            logger.error(f"Error inesperado al procesar {repo_url}: {e}")
            logger.error(traceback.format_exc())
            failed_backups += 1
        finally:
            if os.path.exists(repo_dir):
                shutil.rmtree(repo_dir)
            if os.path.exists(zip_path):
                os.remove(zip_path)
            end_repo_time = datetime.datetime.now()
            duration = (end_repo_time - start_repo_time).total_seconds()
            repo_results.append({
                'RepoName': repo_name,
                'RepoURL': repo_url,
                'Status': status,
                'Duration': duration,
                'ErrorMessage': error_message
            })
            logger.info(f"Finalizado procesamiento del repositorio: {repo_name} con estado: {status}")

    max_workers = min(THREAD_POOL_SIZE, os.cpu_count() or 1)
    logger.info(f"Usando {max_workers} trabajadores para procesar los repositorios.")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_repository, repo_url): repo_url for repo_url in repo_list}
        for future in as_completed(futures):
            repo_url = futures[future]
            try:
                future.result()
            except Exception as e:
                logger.error(f"Error en el procesamiento de {repo_url}: {e}")

    if os.path.exists(TMP_DIR):
        shutil.rmtree(TMP_DIR)
    
    logger.info("Obteniendo lista de backups existentes...")
    try:
        blob_service_client = BlobServiceClient(
            f"https://{AZURE_STORAGE_ACCOUNT}.blob.core.windows.net",
            credential=AZURE_STORAGE_KEY
        )
        container_client = blob_service_client.get_container_client(CONTAINER_NAME)
        existing_backups = [blob.name for blob in container_client.list_blobs()]
    except Exception as e:
        logger.error(f"Error al listar los blobs: {e}")
        return

    def should_delete_backup(backup_name):
        try:
            # Extraer la fecha del nombre del backup (formato esperado: YYYY/MM/DD/nombre_backup.zip)
            date_part = '/'.join(backup_name.split('/')[:3])
            backup_date = datetime.datetime.strptime(date_part, '%Y/%m/%d')
            diff_days = (CURRENT_DATE - backup_date).days

            if diff_days <= 7:
                return False
            elif diff_days <= 28 and backup_date.weekday() == 0:
                return False
            elif diff_days <= 365 and backup_date.day == 1:
                return False
            else:
                return True
        except Exception as e:
            logger.warning(f"No se pudo procesar {backup_name}: {e}")
            return False

    for backup in existing_backups:
        if should_delete_backup(backup):
            logger.info(f"Eliminando backup antiguo: {backup}")
            try:
                blob_client = blob_service_client.get_blob_client(container=CONTAINER_NAME, blob=backup)
                blob_client.delete_blob()
            except Exception as e:
                logger.error(f"Error al eliminar {backup}: {e}")

    end_time = datetime.datetime.now()
    total_time = end_time - start_time
    total_time_str = str(total_time).split('.')[0]

    logger.info("Proceso completado.")
    logger.info(f"Tiempo total del proceso: {total_time_str}")

    logger.info("Insertando datos en MSSQL...")
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO BackupTasks (StartTime, EndTime, TotalRepos, SuccessfulBackups, FailedBackups)
            VALUES (?, ?, ?, ?, ?)
        ''', start_time, end_time, total_repos, successful_backups, failed_backups)
        task_id = cursor.execute('SELECT MAX(TaskID) FROM BackupTasks').fetchone()[0]

        for repo_result in repo_results:
            cursor.execute('''
                INSERT INTO RepositoryBackups (TaskID, RepoName, RepoURL, Status, Duration, ErrorMessage)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', task_id, repo_result['RepoName'], repo_result['RepoURL'], repo_result['Status'], repo_result['Duration'], repo_result['ErrorMessage'])
        conn.commit()
    except Exception as e:
        logger.error(f"Error al insertar datos en MSSQL: {e}")
        conn.rollback()
    finally:
        conn.close()

    table_data = [
        ["Completados", successful_backups],
        ["Con Errores", failed_backups],
        ["Total", total_repos]
    ]
    table = tabulate(table_data, headers=["Estado", "Cantidad"], tablefmt="pretty")

    grafana_dashboard_url = "<Grafana-Dashboard-URL>"
    
    try:
        webhook = DiscordWebhook(url=DISCORD_WEBHOOK_URL)
        embed = DiscordEmbed(title="BitBackup - Reporte de Respaldo", color='03b2f8')
        embed.add_embed_field(name="Fecha", value=DATE_STR)
        embed.add_embed_field(name="Hora", value=TIME_STR)
        embed.add_embed_field(name="Tiempo Total", value=total_time_str)
        embed.add_embed_field(name="Detalle", value=f"```{table}```", inline=False)
        embed.add_embed_field(name="Reporte", value=f"[Ver Dashboard]({grafana_dashboard_url})", inline=False)
        webhook.add_embed(embed)
        response = webhook.execute()
        if response.status_code == 200:
            logger.info("Reporte enviado exitosamente a Discord.")
        else:
            logger.error(f"Error al enviar el reporte a Discord: {response.status_code}")
    except Exception as e:
        logger.error(f"Error al enviar el reporte a Discord: {e}")

# OLD (Todos los dias)
# schedule.every().day.at("02:00").do(perform_backup)
# Actualizacion v.1.2411.1101
# Ahora solo de lunes a viernes:
schedule.every().monday.at("02:00").do(perform_backup)
schedule.every().tuesday.at("02:00").do(perform_backup)
schedule.every().wednesday.at("02:00").do(perform_backup)
schedule.every().thursday.at("02:00").do(perform_backup)
schedule.every().friday.at("02:00").do(perform_backup)

if __name__ == "__main__":
    title = pyfiglet.figlet_format(f"\n {APP_NAME}", font="standard")
    logger.info(Fore.CYAN + title + Style.RESET_ALL)
    logger.info(Fore.GREEN + f"Version: {VERSION}" + Style.RESET_ALL)
    logger.info(Fore.GREEN + f"{DESCRIPTION}\n" + Style.RESET_ALL)
    
    if AUTOEXECUTE:
        logger.info("AUTOEXECUTE habilitado. Ejecutando respaldo de Bitbucket...")
        perform_backup()
    
    logger.info("Iniciando el programador de tareas.")
    while True:
        schedule.run_pending()
        time.sleep(60)
