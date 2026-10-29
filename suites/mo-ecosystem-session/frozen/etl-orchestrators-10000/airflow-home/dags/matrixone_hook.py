from airflow.sdk import DAG
from airflow.providers.standard.operators.python import PythonOperator
from datetime import datetime,timedelta,timezone
B='/workspace/work/etl-orchestrators-10000'
def execute_matrix(port,inject=False):
 import runpy,sys
 old=sys.argv[:];sys.argv=[B+'/worker.py','--component','airflow','--port',str(port)]+(['--inject-retry'] if inject else [])
 try:runpy.run_path(B+'/worker.py',run_name='__main__')
 finally:sys.argv=old
with DAG('matrixone_ecosystem_hook_2000',start_date=datetime(2026,10,10,tzinfo=timezone.utc),schedule=None,catchup=False,max_active_runs=1,tags=['matrixone','native-hook-2000']) as dag:
 mo=PythonOperator(task_id='matrixone_1000',python_callable=execute_matrix,op_kwargs={'port':6001,'inject':True},retries=1,retry_delay=timedelta(seconds=3),execution_timeout=timedelta(minutes=25))
 mysql=PythonOperator(task_id='mysql_control_1000',python_callable=execute_matrix,op_kwargs={'port':13306},retries=1,retry_delay=timedelta(seconds=3),execution_timeout=timedelta(minutes=25))
 mo>>mysql
