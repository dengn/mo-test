from pathlib import Path
B=Path(__file__).resolve().parent
s=(B.parent/'etl-10000/matrix.py').read_text();s=s[:s.index("if __name__=='__main__':")];s=s.replace('/etl10000','/heavy5000').replace('label VARCHAR(256)','label VARCHAR(8192)');s=s.replace("SCENARIOS=['append','chunked_append','native_transform','staging_merge','tombstone_delete']","SCENARIOS=['append','chunked_append','parallel_chunked','native_transform','staging_merge','tombstone_delete','delete_reinsert','duplicate_rollback_retry','schema_add','replay_merge']")
(B/'core.py').write_text(s)
