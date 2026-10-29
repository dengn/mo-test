from runtime import *
(B/'monitor.pid').write_text(str(os.getpid()));start=time.monotonic()
while not (B/'monitor.stop').exists():
 with (B/'resources.jsonl').open('a') as f:f.write(json.dumps(resources(),ensure_ascii=False)+'\n')
 if time.monotonic()-start>7200:break
 time.sleep(2)
