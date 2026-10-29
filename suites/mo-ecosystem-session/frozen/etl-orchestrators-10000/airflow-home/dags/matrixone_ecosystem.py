from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator
from datetime import datetime,timedelta,timezone
B='/workspace/work/etl-orchestrators-10000'
with DAG('matrixone_ecosystem_2000',start_date=datetime(2026,10,10,tzinfo=timezone.utc),schedule=None,catchup=False,max_active_runs=1,tags=['matrixone','synthetic-2000']) as dag:
 mo=BashOperator(task_id='matrixone_1000',bash_command=f'{B}/venv/bin/python {B}/worker.py --component airflow --port 6001 --inject-retry',retries=1,retry_delay=timedelta(seconds=3),execution_timeout=timedelta(minutes=25))
 mysql=BashOperator(task_id='mysql_control_1000',bash_command=f'{B}/venv/bin/python {B}/worker.py --component airflow --port 13306',retries=1,retry_delay=timedelta(seconds=3),execution_timeout=timedelta(minutes=25))
 mo>>mysql
