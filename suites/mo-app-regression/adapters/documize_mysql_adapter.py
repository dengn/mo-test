"""Local packet-preserving native Documize MySQL adapter; never rewrites results/auth."""
import argparse,asyncio,hashlib,json,pathlib,re,signal

def rewrite(sql):
    changes=[]
    engine=re.fullmatch(r'\s*ALTER\s+TABLE\s+(config|permission|category|categorymember|role|rolemember|search)\s+ENGINE\s*=\s*InnoDB\s*;?\s*',sql,re.I)
    if engine:
        # MatrixOne owns its storage engine. Omit only this vendor-specific option;
        # execute a real commit and table-existence query, never fabricate an OK.
        return 'COMMIT;\nSELECT 1 FROM `'+engine.group(1)+'` LIMIT 0',['omit_mysql_physical_engine_selection_real_table_check']
    if re.fullmatch(r'\s*OPTIMIZE\s+TABLE\s+search\s*;?\s*',sql,re.I):
        return 'COMMIT;\nSELECT 1 FROM `search` LIMIT 0',['omit_mysql_optimize_real_table_check_no_compaction_claim']
    sql,count=re.subn(r'^(\s*ALTER\s+TABLE\s+)config\b',r'\1`config`',sql,flags=re.I)
    if count:changes.append('quote_native_config_table_identifier')
    if re.match(r'^\s*SELECT\b',sql,re.I) and re.search(r'\bFROM\s+dmz_org\b',sql,re.I):
        sql,count=re.subn(r'(\bAS\s+)subscription\b',r'\1`subscription`',sql,flags=re.I)
        if count:changes.append('quote_native_subscription_result_alias')
        sql,count=re.subn(r"coalesce\(\s*(c_authconfig|c_sub)\s*,\s*(?:'\{\}'|JSON_UNQUOTE\('\{\}'\))\s*\)",r"coalesce(\1,CAST('{}' AS JSON))",sql,flags=re.I)
        if count:changes.append('typed_JSON_empty_object_default')
    if re.match(r'^\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?search`?\s*\(',sql,re.I):
        if ('FULLTEXT' in sql.upper() and 'PRIMARY KEY' not in sql.upper()
                and re.search(r'`id`\s+(?:CHAR\(16\)|INT UNSIGNED)\s+NOT NULL',sql,re.I)
                and re.search(r'UNIQUE INDEX `idx_search_id`\s*\(`id` ASC\)',sql,re.I)):
            needle=re.search(r'(\s*FULLTEXT(?:\s+INDEX\s+`idx_search_content`)?\s*\((?:`pagetitle`\s*,\s*`body`|`content`)\)\s*\))',sql,re.I)
            if needle:
                sql=sql[:needle.start()]+'\n PRIMARY KEY (`id`),'+sql[needle.start():]
                changes.append('search_existing_unique_not_null_id_primary_key')
    # Two pinned legacy schema declarations, preserving width and Unicode-capable storage.
    if re.match(r'^\s*(CREATE|ALTER)\s+TABLE\b',sql,re.I):
        patterns=[(r'(`note`\s+)NVARCHAR(\s*\(2000\))',r'\1VARCHAR\2'),
                  (r'(`externalid`\s+)NVARCHAR(\s*\(1000\))',r'\1VARCHAR\2')]
        for pattern,replacement in patterns:
            sql,count=re.subn(pattern,replacement,sql,flags=re.I)
            if count:changes.append('native_nvarchar_width_preserved')
    # MySQL DDL implicitly commits; MatrixOne requires this explicit boundary.
    # The real server executes both statements and the native client drains both results.
    if re.match(r'^\s*(CREATE|ALTER|DROP|RENAME|TRUNCATE)\s+(TABLE|INDEX)\b',sql,re.I):
        sql='COMMIT;\n'+sql
        changes.append('actual_mysql_implicit_DDL_commit_boundary')
    return sql,changes

async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,required=True)
    parser.add_argument('--audit',type=pathlib.Path,required=True);args=parser.parse_args()
    args.audit.parent.mkdir(parents=True,exist_ok=True)
    audit=args.audit.open('x');args.audit.chmod(0o600)
    async def handle(reader,writer):
        upstream=None;tasks=[]
        try:
            remote,upstream=await asyncio.open_connection('127.0.0.1',6001)
            async def responses():
                while data:=await remote.read(256*1024):writer.write(data);await writer.drain()
            async def requests():
                while True:
                    header=await reader.readexactly(4);size=int.from_bytes(header[:3],'little')
                    payload=await reader.readexactly(size)
                    if header[3]==0 and payload[:1] in (b'\x03',b'\x16') and size<1024*1024:
                        try:original=payload[1:].decode('utf-8')
                        except UnicodeDecodeError:original=None
                        if original is not None:
                            updated,changes=rewrite(original)
                            if changes:
                                audit.write(json.dumps({'changes':changes,'original_sha256':hashlib.sha256(original.encode()).hexdigest(),
                                    'adapted_sha256':hashlib.sha256(updated.encode()).hexdigest(),'original_DDL':original,'adapted_DDL':updated})+'\n');audit.flush()
                                payload=payload[:1]+updated.encode();header=len(payload).to_bytes(3,'little')+header[3:]
                    upstream.write(header+payload);await upstream.drain()
            tasks=[asyncio.create_task(responses()),asyncio.create_task(requests())]
            await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
        except (OSError,asyncio.IncompleteReadError):pass
        finally:
            for task in tasks:task.cancel()
            if tasks:await asyncio.gather(*tasks,return_exceptions=True)
            writer.close()
            if upstream:upstream.close()
    server=await asyncio.start_server(handle,'127.0.0.1',args.port)
    stop=asyncio.Event();loop=asyncio.get_running_loop()
    for sig in (signal.SIGTERM,signal.SIGINT):loop.add_signal_handler(sig,stop.set)
    print('Local native MySQL adapter ready',flush=True)
    try:
        async with server:await stop.wait()
    finally:audit.close()

if __name__=='__main__':asyncio.run(main())
