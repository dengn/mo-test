"""Owned loopback packet relay: fixed NVARCHAR migration DDL only, original auth/results."""
import argparse
import asyncio
import hashlib
import json
import pathlib
import re
import signal

IDENT=r'(?:`[A-Za-z0-9_]+`|[A-Za-z0-9_]+)'
NVARCHAR=re.compile(rf'^(ALTER TABLE {IDENT} MODIFY {IDENT} )NVARCHAR(\(\d+\) NOT NULL;?)$',re.I)


async def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,required=True)
    parser.add_argument('--upstream-host',required=True);parser.add_argument('--upstream-port',type=int,required=True)
    parser.add_argument('--audit',type=pathlib.Path,required=True);args=parser.parse_args()
    with args.audit.open('x') as audit:
        args.audit.chmod(0o600)
        async def client(reader,writer):
            backend=None;tasks=[]
            try:
                upstream,backend=await asyncio.open_connection(args.upstream_host,args.upstream_port)
                async def forward(source,target,adapt):
                    while True:
                        header=await source.readexactly(4);length=int.from_bytes(header[:3],'little');body=await source.readexactly(length)
                        if adapt and header[3]==0 and body[:1] in {b'\x03',b'\x16'}:
                            try:sql=body[1:].decode('utf8')
                            except UnicodeDecodeError:sql=None
                            if sql is not None:
                                replacement=NVARCHAR.sub(r'\1VARCHAR\2',sql)
                                if replacement!=sql:
                                    audit.write(json.dumps({'rule':'nvarchar_width_preserved','original_sql':sql,'adapted_sql':replacement,
                                        'original_sha256':hashlib.sha256(sql.encode()).hexdigest()})+'\n');audit.flush();body=body[:1]+replacement.encode()
                        target.write(len(body).to_bytes(3,'little')+header[3:]+body);await target.drain()
                tasks=[asyncio.create_task(forward(reader,backend,True)),asyncio.create_task(forward(upstream,writer,False))]
                done,_=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
                for task in done:task.result()
            except(OSError,asyncio.IncompleteReadError):pass
            finally:
                for task in tasks:task.cancel()
                if tasks:await asyncio.gather(*tasks,return_exceptions=True)
                writer.close()
                if backend:backend.close()
        server=await asyncio.start_server(client,'127.0.0.1',args.port);stop=asyncio.Event();loop=asyncio.get_running_loop()
        for sig in(signal.SIGTERM,signal.SIGINT):loop.add_signal_handler(sig,stop.set)
        print('Owned MatrixOne relay ready',flush=True)
        async with server:await stop.wait()


if __name__=='__main__':asyncio.run(main())
