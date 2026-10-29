import pathlib,sys
B=pathlib.Path(__file__).resolve().parent
from fivetran_connector_sdk import connector_helper as ch
ch.config_root_dir_helper=lambda:str(B/'sdk-cache')
print(ch.ensure_tester_installed(),flush=True)
