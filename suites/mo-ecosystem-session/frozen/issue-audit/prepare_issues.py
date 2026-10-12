import json
from pathlib import Path

B=Path(__file__).parent
SHA='652c643666428f1c434e03369834f2a9bead7c27'
MAIN='dd38098853ea197699ed3fac3e69dc53975ac061'
BASE='https://github.com/matrixorigin/matrixone'
ENV=f'''## 测试条件与证据边界

- 测试日期：2026-10-10 至 2026-10-11；本地 Linux x86_64 / Debian 13，单节点 standalone（1 CN / 1 TN / 1 LogService），非生产实例。
- **实际运行版本**：本地 MatrixOne checkout `{SHA}`。没有把其他 SHA 的源码检查冒充运行测试；修复验收需要在最新 main 重跑并记录 SHA。
- 客户端：MySQL 文本协议，PyMySQL 1.2.3；本地端口 6001，autocommit=True。测试数据为人工构造的边界值。
- 类型矩阵使用 `SET time_zone='+00:00'`。JSON EOF 专项实测 sql_mode：`ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION,NO_ZERO_DATE,NO_ZERO_IN_DATE,ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,ENABLE_BOOL_SUMAVG`。其他专项未单独保存完整 sql_mode，不能据此宣称所有模式都已测过；下列重跑建议显式使用严格模式并保存模式值。
- 对照（仅在正文明确注明已运行的地方使用）：本地真实 MySQL 8.4 容器。不能把“建议对照”当成已有 MySQL 复现。
- 本轮是数据正确性与兼容性诊断，没有做吞吐、p99、HA、长稳或跨系统 exactly-once 认证。
- 报告中的本地 receipt 文件用于说明原始证据来源，**不是公开下载链接**；复现所需输入和步骤在正文内提供。

''' 
PARITY=f'''相关源码曾与公开 main `{MAIN}` 按完整文件内容核对一致：`decimal.go`、`external.go`、`reader_csv.go`、`reader_arrow.go`。这只证明这些文件一致，不等于在该 main 部署运行过，也不证明整个依赖链一致。

'''
CONN='''import os, pymysql
from pathlib import Path
root = Path("/tmp/mo-issue-fixtures"); root.mkdir(exist_ok=True)
d = pymysql.connect(host=os.getenv("MO_HOST","127.0.0.1"),
    port=int(os.getenv("MO_PORT","6001")), user=os.getenv("MO_USER","root"),
    password=os.environ["MO_PASSWORD"], autocommit=True, charset="utf8mb4")
c = d.cursor()
c.execute("CREATE DATABASE IF NOT EXISTS ecosystem_issue_repro")
c.execute("USE ecosystem_issue_repro")
c.execute("SET time_zone='+00:00'")
c.execute("SET sql_mode='STRICT_TRANS_TABLES'")
'''
PRE='''复现前安装正文指定的 Python 依赖，并设置 `MO_PASSWORD`（不要把真实密码写进 issue）。下列文件路径必须在 mo-service 所在机器可读；容器部署请挂载同一目录并使用服务端可见的绝对路径。每个脚本使用独立测试表。

'''
issues=[]
def add(key,title,body,kind='bug'):
    issues.append(dict(key=key,title=title,body=body,labels=['kind/'+kind]))
def links(items):
    return '\n'.join('- '+text+f' [{"PR " if pr else "#"}{n}]({BASE}/{"pull" if pr else "issues"}/{n})' for n,text,pr in items)

add('enum_set','[Bug]: CSV/JSONLINE LOAD silently converts valid empty ENUM/SET values to NULL',ENV+PARITY+'''## 现象与预期

`ENUM('red','中文','')` 中声明的空字符串和 `SET('a','中文')` 的空集合都合法，必须与 SQL NULL 区分。

| 输入/路径 | 原始结果 |
|---|---|
| ENUM 普通 INSERT | `['red','中文','',NULL]`，正确 |
| ENUM CSV / JSONLINE | `['red','中文',NULL,NULL]`，空字符串丢失 |
| SET 普通 INSERT | `['','a','a,中文',NULL]`，正确 |
| SET CSV / JSONLINE | `[NULL,'a','a,中文',NULL]`，空集合丢失 |
| ENUM Parquet string | 正确保留空字符串 |
| SET Parquet string | 拒绝，`strconv.ParseUint: parsing "": invalid syntax`，不能算通过的对照 |
| CSV/JSONLINE → VARCHAR 暂存 → 原生 typed INSERT | ENUM 和 SET 共 4 个适配用例均保留空值与 NULL 区别 |

LOAD 本身完成；测试失败来自读回比对，相关表已经写入 4 行。建议优先级 P0：成功导入却静默改变语义。

## 完整复现

依赖 `PyMySQL==1.2.3`。'''+PRE+'```python\n'+CONN+'''import csv, json
for name,ddl,vals in [
    ('enum', "ENUM('red','中文','')", ['red','中文','',None]),
    ('set', "SET('a','中文')", ['', 'a','a,中文',None])]:
    for fmt in ['csv','jsonline']:
        table='empty_'+name+'_'+fmt
        c.execute('DROP TABLE IF EXISTS '+table)
        c.execute(f'CREATE TABLE {table}(id INT PRIMARY KEY,v {ddl})')
        p=root/(table+'.'+fmt)
        if fmt=='csv':
            with p.open('w',newline='',encoding='utf-8') as f:
                csv.writer(f,quoting=csv.QUOTE_ALL).writerows(
                    (i+1,v if v is not None else '\\N') for i,v in enumerate(vals))
            opts=" FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '\"'"
            extra=''
        else:
            p.write_text(''.join(json.dumps({'id':i+1,'v':v},ensure_ascii=False)+'\\n'
                for i,v in enumerate(vals)),encoding='utf-8')
            opts=''; extra=",'jsondata'='object'"
        c.execute(f"LOAD DATA INFILE {{'filepath'='{p}','format'='{fmt}'{extra}}} INTO TABLE {table}{opts}")
        c.execute('SHOW WARNINGS'); print(table,'warnings',c.fetchall())
        c.execute(f'SELECT id,v,v IS NULL FROM {table} ORDER BY id')
        print(table,c.fetchall())
        control=table+'_native'
        c.execute('DROP TABLE IF EXISTS '+control)
        c.execute(f'CREATE TABLE {control}(id INT PRIMARY KEY,v {ddl})')
        c.executemany('INSERT INTO '+control+' VALUES(%s,%s)',list(enumerate(vals,1)))
        c.execute(f'SELECT id,v,v IS NULL FROM {control} ORDER BY id')
        print(control,c.fetchall())
d.close()
```

上面的独立脚本根据原测试步骤整理，尚未另行执行；原类型矩阵和 4 个暂存适配用例已经执行。

## 源码定位与验收

`pkg/sql/colexec/external/external.go:getColData`：trimSpace 白名单不含 ENUM；SET 使用带 Enumvalues 的 uint64 存储，空文本在进入 ENUM/SET 转换前被通用逻辑变成 NULL。应按逻辑类型处理空值，保留显式 NULL/null_map 语义。

- [ ] CSV、JSONLINE 两条入口分别覆盖 ENUM 声明空成员、SET 空集合、SQL NULL、Unicode 成员。
- [ ] 对照普通 INSERT；带引号空值、NULL 标记和 whitespace 成员分别验证，不能用“全部空字符串转零/NULL”规避。
- [ ] 明确 nullable / NOT NULL、串行 / 并行和严格 / 非严格的契约；验收逐值比对并保存 SHOW WARNINGS。

## 关联与区别
'''+links([(29768,'相关 NULL 语义问题，但它是并行 JSONLINE 显式 NULL→0/false，不覆盖本问题：',False),(29262,'相关 external NULL append 错误处理，不是本处空值归一化：',False),(27746,'Flink 类型与 NULL 兼容性认证跟踪：',False)])+'''

原始 receipt：`type-matrix-result.json`、`final-adaptations-result.json`。
''')

add('decimal','[Bug]: Decimal128 text parser counts leading zero and loses DECIMAL(38,38) precision',ENV+PARITY+'''## 现象与预期

合法定点文本 `0.00000000000000000000000000000000000001` 在 DECIMAL(38,38) 中应精确保存为 `1E-38`，实际字符串参数、CSV、JSONLINE 写入为 `0E-38`。这是静默精度丢失，建议 P0。

| 文本或路径 | 已运行结果 |
|---|---|
| `0.` + 37 个 `0` + `1`，字符串参数 / CSV / JSONLINE | 成功但变成零 |
| `0.` + 38 个 `9`，字符串参数 / CSV / JSONLINE | 合法值被拒绝为越界 |
| `.` + 38 个 `9`，字符串参数 | 精确保留 |
| `-0.` + 38 个 `9` / `-.` + 38 个 `9` | 前者拒绝，后者精确保留 |
| `.` + 37 个 `0` + `1`，以及 `1E-38` | 精确保留 |
| 类型化 Parquet/Arrow DECIMAL(38,38)、同类型 INSERT SELECT | 精确保留对应边界值 |

## 完整复现

依赖 `PyMySQL==1.2.3`；使用字符串绑定隔离数字字面量 binder。'''+PRE+'```python\n'+CONN+'''import csv,json
tiny='0.'+'0'*37+'1'
variants=[tiny,'.'+'0'*37+'1','1E-38','0.'+'9'*38,'.'+'9'*38,
    '-0.'+'9'*38,'-.'+'9'*38,'0.1']
c.execute('DROP TABLE IF EXISTS dec_native')
c.execute('CREATE TABLE dec_native(id INT PRIMARY KEY,v DECIMAL(38,38))')
for i,text in enumerate(variants,1):
    try:
        c.execute('INSERT INTO dec_native VALUES(%s,%s)',(i,text))
        c.execute('SELECT CAST(v AS CHAR) FROM dec_native WHERE id=%s',(i,))
        print(repr(text),'stored',c.fetchone())
    except pymysql.MySQLError as e: print(repr(text),'rejected',str(e))
for fmt in ['csv','jsonline']:
    table='dec_'+fmt; p=root/(table+'.'+fmt)
    c.execute('DROP TABLE IF EXISTS '+table)
    c.execute(f'CREATE TABLE {table}(id INT PRIMARY KEY,v DECIMAL(38,38))')
    if fmt=='csv':
        with p.open('w',newline='') as f: csv.writer(f).writerow([1,tiny])
        extra='';opts=" FIELDS TERMINATED BY ','"
    else:
        p.write_text(json.dumps({'id':1,'v':tiny})+'\\n')
        extra=",'jsondata'='object'";opts=''
    c.execute(f"LOAD DATA INFILE {{'filepath'='{p}','format'='{fmt}'{extra}}} INTO TABLE {table}{opts}")
    c.execute('SHOW WARNINGS'); print(fmt,'warnings',c.fetchall())
    c.execute(f'SELECT CAST(v AS CHAR) FROM {table}'); print(fmt,c.fetchall())
d.close()
```

脚本根据已运行原用例整理；字符串变体和两条文本文件导入已有独立 receipt。

## 定位、修复边界与验收

`pkg/container/types/decimal.go:Parse128` 的 width 累计包含小数点前无意义的 `0`；到 width==38 提前舍入/结束，导致最低有效位被丢弃。不能把合法的前导零写法要求为用户适配格式；去掉小数点前的零只作为诊断对照。

- [ ] 正负 `1E-38`、正负最大 38 位纯小数、NULL、0、普通小数，字符串参数和 CSV/JSONLINE 均精确。
- [ ] 前导零、无前导零、科学计数法表达同一数值时结果一致；额外前导零也不能耗尽有效精度。
- [ ] 真正超出精度的输入仍按契约舍入/拒绝；不能影响整数 38 位边界、DECIMAL256 或指数溢出处理。
- [ ] 验收使用 Decimal/定点字符串，不经 float；保留 columnar 对照与同类型 INSERT SELECT。

## 关联与区别
'''+links([(28765,'已关闭的 DECIMAL256 未加引号字面量 binder 截断，与这里的 Decimal128 字符串解析不同：',False),(25473,'已关闭的 Parquet decimal scale 错误，与本处文本前导零不同：',False),(29550,'已关闭的大写 E CAST 问题，本复现不需要指数：',False),(28771,'已关闭的 prepared decimal 元数据归一化问题：',False),(28590,'已关闭的 CSV/JSONLINE DECIMAL256 不支持问题，本轮 DECIMAL65 文本路径已通过：',False)])+'''

原始 receipt：`advanced-probes-result.json`、`decimal-fixed-notation-result.json`、`semantic-retest-result.json`。
''')

add('json_eof','[Bug]: Strict JSONLINE LOAD succeeds and silently drops malformed final records at EOF',ENV+PARITY+'''## 现象

严格模式下，JSONLINE 文件包含一条完整记录和一条残缺末尾记录，LOAD DATA 成功、affected_rows=1、SHOW WARNINGS 为空，只保存第一条。只有残缺记录的文件也成功，affected_rows=0。

建议 P0：文件截断可能被当成成功导入，任务状态无法发现漏行。

## 原始测试过程和全部对照

目标表 `(id INT PRIMARY KEY,v JSON)`，每个输入用独立表；捕获 LOAD 的成功/错误、affected_rows，立即 SHOW WARNINGS，随后读取全部行，最后追加合法行验证连接/表可继续使用。

| 文件内容类别 | LOAD 状态 | 已保存原始行 | warning |
|---|---|---|---|
| 2 条完整 JSON | success / 2 | 2 行 | 无 |
| 完整记录 + `this is not json` | rejected / 20301 | 0 行 | invalid input |
| 完整记录 + 末尾缺一个 `}` | **success / 1** | **只剩第一行** | **无** |
| 只有残缺记录 | **success / 0** | **0 行** | **无** |
| 完整 + 残缺 + 下一条完整 JSON | rejected / 20301 | 0 行 | invalid input |
| 完整 + `{"id":2,"v":{invalid}}` | **success / 1** | **只剩第一行** | **无** |

所有用例后续合法 INSERT 均成功。末尾残缺的同一文件经 external SELECT 显式投影错误列后返回 2 行：第一行正常，第二行错误 `invalid input: incomplete json record`，说明容错查询能保留 rejected-record accounting，但不能据此宣称严格 LOAD 修复。

## 完整复现

依赖 PyMySQL 1.2.3。'''+PRE+'```python\n'+CONN+'''variants={
 'valid':'{"id":1,"v":{}}\\n{"id":2,"v":{"a":1}}\\n',
 'bare_bad':'{"id":1,"v":{}}\\nthis is not json\\n',
 'incomplete_last':'{"id":1,"v":{}}\\n{"id":2,"v":{"a":1}\\n',
 'incomplete_only':'{"id":2,"v":{"a":1}\\n',
 'incomplete_then_valid':'{"id":1,"v":{}}\\n{"id":2,"v":{"a":1}\\n{"id":3,"v":{}}\\n',
 'malformed_closed':'{"id":1,"v":{}}\\n{"id":2,"v":{invalid}}\\n'}
for name,text in variants.items():
    p=root/(name+'.jsonl');p.write_text(text)
    table='eof_'+name;c.execute('DROP TABLE IF EXISTS '+table)
    c.execute(f'CREATE TABLE {table}(id INT PRIMARY KEY,v JSON)')
    try:
        n=c.execute(f"LOAD DATA INFILE {{'filepath'='{p}','format'='jsonline','jsondata'='object'}} INTO TABLE {table}")
        print(name,'success',n)
    except pymysql.MySQLError as e:print(name,'rejected',str(e))
    c.execute('SHOW WARNINGS');print('warnings',c.fetchall())
    c.execute(f'SELECT id,v FROM {table} ORDER BY id');print('rows',c.fetchall())
p=root/'incomplete_last.jsonl'
c.execute('DROP TABLE IF EXISTS eof_error_source')
c.execute(f"CREATE EXTERNAL TABLE eof_error_source(id INT,v JSON) INFILE{{'filepath'='{p}','format'='jsonline','jsondata'='object'}}")
c.execute('SELECT id,v,__mo_file_line,__mo_error_message,__mo_error_text FROM eof_error_source')
print('explicit rejects',c.fetchall());d.close()
```

## 与已有实现的关系

关联 feature #27517 要求未请求错误列时维持严格失败语义。PR #27609 已合并，正文说：

> Text held over that the file never completes is reported at EOF rather than dropped.

当前 `reader_csv.go:makeBatchRows` 严格路径仍在 truncated 且 !Tolerate 时 continue 并保留 prevStr；物理 io.EOF 分支直接 close/break，没有检查 pending prevStr。容错路径则立即清空 prevStr 并生成 reject row。这是**严格路径修复遗漏**；尚无证据证明是该 PR 之后引入的新回归。

## 验收

- [ ] 严格 LOAD/外表扫描不能成功吞掉残缺末尾；必须返回可定位的错误。
- [ ] 容错投影的完整行+reject 行总数与输入记录一致，错误文本、原文和行号准确。
- [ ] 覆盖末尾有/无换行、纯残缺文件、batch boundary、多文件最后一条和合法 continuation 语义；这些扩展是待验收，不是已测通过。
- [ ] bareword / 闭合但语法坏 / 真正截断分别有回归；逐例保存 rows、affected_rows、warnings。

## 关联
'''+links([(27517,'错误列与严格/容错契约：',False),(27609,'已合并但严格 EOF 路径仍遗漏的实现：',True),(29768,'另一个 JSONLINE 问题（并行 NULL→零），触发条件不同：',False)])+'''

原始 receipt：`jsonline-eof-result.json`，6 个输入变体及显式 error projection 均实测。
''')

add('invalid_identifier','[Bug]: Invalid UTF-8 table identifier is admitted into catalog and causes DROP DATABASE panic',ENV+'''## 实测与影响

通过 PyMySQL bytes SQL 发送表名 `t_\\xe3g`（hex `745FE367`，无效 UTF-8），CREATE TABLE 被接受，mo_catalog.mo_tables 保存了原始名字。随后 DROP DATABASE 返回 recovered internal panic，目录清理失败。

建议 P0：入口接受无法由后续目录操作正确处理的对象名，破坏 DDL 可管理性。这里不是合法 Unicode 标识符兼容性问题。

该复现来自此前同一运行版本测试；**没有声称最新公开 main 重部署后也复现**，本问题涉及的目录代码没有包含在类型文件 parity 核对范围中。

## 复现条件与完整步骤

使用隔离的、可丢弃的临时实例，避免在业务数据库目录制造无法清理的对象。`use_unicode=False`，传入 bytes SQL，不经过字符串 UTF-8 编码。

```python
import os,pymysql
d=pymysql.connect(host=os.getenv('MO_HOST','127.0.0.1'),
    port=int(os.getenv('MO_PORT','6001')),user=os.getenv('MO_USER','root'),
    password=os.environ['MO_PASSWORD'],autocommit=True,use_unicode=False)
c=d.cursor();c.execute('CREATE DATABASE raw_name_probe')
sql=b'CREATE TABLE raw_name_probe.t_\\xe3g(id INT)'
print('wire hex',sql.hex())
c.execute(sql)  # actual: accepted
c.execute("SELECT hex(relname) FROM mo_catalog.mo_tables WHERE reldatabase='raw_name_probe'")
print(c.fetchall())  # actual: 745FE367
try:c.execute('DROP DATABASE raw_name_probe')
except pymysql.MySQLError as e:print(str(e))
d.close()
```

实际 wire hex：`435245415445205441424c45207261775f6e616d655f70726f62652e745fe36728696420494e5429`。

## 原始错误与控制

```text
20101 internal error: panic delete table failed: query failed
pkg/vm/engine/disttae/txn_database.go:267 (*txnDatabase).deleteTable
pkg/vm/engine/disttae/txn_database.go:185 (*txnDatabase).Delete
pkg/sql/compile/ddl.go:4788 dropTableSingleResolved
pkg/sql/compile/ddl.go:527 dropDatabaseRelations
pkg/sql/compile/ddl.go:384 DropDatabase
```

上述 panic 由 SQL 执行器恢复并返回错误，**没有观察到 mo-service 进程崩溃**。合法 UTF-8 名称控制（Unicode、中文等）创建/删除成功；原非法对象不能正常 DROP DATABASE。目录删除路径构造的查询无法解析该名字，是需要进一步验证的定位线索，不应仅靠 recover 隐藏问题。

## 预期与验收

- [ ] 非法 UTF-8 名称应在入目录前以明确 SQL 错误拒绝；失败后不留下对象。
- [ ] 合法 Unicode 名称继续可创建、查询、重命名和删除。
- [ ] 对已经存在的非法名字提供可诊断的清理/修复路径，避免目录操作 panic。
- [ ] 记录原始 wire bytes；覆盖 table/database/column 等标识符、文本/预处理协议和目录恢复，扩展范围需单独实测。

## 关联与区别
'''+links([(25302,'非法 UTF-8 VARCHAR 数据内容被接受，不覆盖标识符目录清理：',False),(26715,'合法未加引号 Unicode 标识符被拒绝，方向与本问题相反：',False),(26677,'ODBC Unicode/元数据契约背景，不能把本问题归为驱动字符串转换：',False)])+'''

原始 receipt：`raw-name-result.json`、`unicode-ddl-result.json`。
''')

add('time_import','[Bug]: External file LOAD bypasses TIME assignment bounds enforced by native INSERT',ENV+PARITY+'''## 现象与预期

TIME(6) 普通 INSERT 会拒绝超出 `±838:59:59.000000` 的值；相同值通过 CSV、JSONLINE 和 Parquet duration 导入能够落表。文件入口与列赋值的值域契约不一致，建议 P1。

原始输入是 `-838:59:59.999999`、`838:59:59.999999`、`-00:00:00.000001`、NULL。CSV 读回的 Python timedelta 分别为 `-35 days, 1:00:00.000001`、`34 days, 22:59:59.999999`、`-1 day, 23:59:59.999999`、None。前两个确已保存端点外的微秒，不是 display-only 差异。

普通字符串 INSERT 已测：端点 `838:59:59.000000` 接受，`±838:59:59.999999` 与 `839:00:00.000000` 拒绝，报 1690 data out of range；真实 MySQL 8.4 严格模式普通 INSERT 对照也拒绝。原测试未使用 MySQL 运行 MatrixOne 专有文件语法。

## 复现

依赖 PyMySQL 1.2.3，Parquet fixture 生成使用 pyarrow 26.0.0。'''+PRE+'```python\n'+CONN+'''import csv,json,datetime
import pyarrow as pa,pyarrow.parquet as pq
vals=['-838:59:59.999999','838:59:59.999999','-00:00:00.000001',None]
c.execute('DROP TABLE IF EXISTS time_native')
c.execute('CREATE TABLE time_native(id INT PRIMARY KEY,v TIME(6))')
for i,v in enumerate(vals,1):
    try:c.execute('INSERT INTO time_native VALUES(%s,%s)',(i,v));print('native accepted',v)
    except pymysql.MySQLError as e:print('native rejected',v,str(e))
for fmt in ['csv','jsonline','parquet']:
    p=root/('time.'+fmt);table='time_'+fmt
    c.execute('DROP TABLE IF EXISTS '+table)
    c.execute(f'CREATE TABLE {table}(id INT PRIMARY KEY,v TIME(6))')
    extra='';opts=''
    if fmt=='csv':
        with p.open('w',newline='') as f:
            csv.writer(f,quoting=csv.QUOTE_ALL).writerows((i+1,v if v is not None else '\\N') for i,v in enumerate(vals))
        opts=" FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '\"'"
    elif fmt=='jsonline':
        p.write_text(''.join(json.dumps({'id':i+1,'v':v})+'\\n' for i,v in enumerate(vals)))
        extra=",'jsondata'='object'"
    else:
        a=[datetime.timedelta(microseconds=x) if x is not None else None
           for x in [-3020399999999,3020399999999,-1,None]]
        pq.write_table(pa.table({'id':pa.array([1,2,3,4],pa.int32()),'v':pa.array(a,pa.duration('us'))}),p)
    c.execute(f"LOAD DATA INFILE {{'filepath'='{p}','format'='{fmt}'{extra}}} INTO TABLE {table}{opts}")
    c.execute('SHOW WARNINGS');print(fmt,'warnings',c.fetchall())
    c.execute(f'SELECT id,v FROM {table} ORDER BY id');print(fmt,c.fetchall())
d.close()
```

## 定位、验收和关联

外部字段/列式转换使用内部 ParseTime/duration 值域，缺少与 MySQLTimeMax 等价的列赋值验证。应共享最新 temporal assignment 契约，严格模式 reject；非严格模式依设计 clamp/diagnostic，不能直接暴露内部数十亿小时范围。

- [ ] CSV、JSONLINE、Parquet 分别测试正负精确端点、端点外 1 微秒、839 小时、-1 微秒、NULL。
- [ ] 严格/非严格的结果与原生列赋值一致，错误行不能留下非法 TIME。
- [ ] 保存 warnings/errors 和持久化值，不只查看格式化字符串；验证 rejected batch 后合法写入可恢复。

'''+links([(28559,'已关闭的 SQL 函数 TIME 边界问题；修复/验收不代表文件导入已覆盖：',False),(28851,'统一 temporal 契约的相关实现，应复用赋值规则而非恢复内部宽范围：',True)])+'''

原始 receipt：`type-matrix-result.json` 的 duration_time 路由、`advanced-probes-result.json` 的 MO/MySQL TIME 边界对照。
''')

add('arrow','[Feature Request]: Expand and document lossless Arrow/Parquet conversion profiles for extended types',ENV+PARITY+'''## 请求与当前契约

在现有 Arrow 静态文件有限 exact-layout 契约之上，增加可选择、可验证的转换 profile，覆盖 Decimal256、nested→JSON 和特殊类型；统一 Arrow/Parquet 的支持矩阵与诊断。建议 P1。

这是**增强请求**：#23684 关闭时已明确有限支持范围；不把所有 unsupported 当成已承诺能力的回归，也不要求静默转换或忽略错误。

## 已运行的路径和结果

Python PyArrow 26.0.0，IPC file `pa.ipc.new_file`，不是 IPC stream/Flight。独立新表，经 LOAD 后逐值读取比对。

| 数据/目标 | 直接入口 | 已验证适配 |
|---|---|---|
| Arrow decimal256(65,30)、(65,0)、(65,65) → DECIMAL65 | 20105 unsupported / no exact long-term conversion | Decimal→精确定点文本→VARCHAR 暂存→显式 CAST，精确 |
| Arrow map/struct/list → JSON | unsupported | JSON 文本暂存→CAST，map 的中文 key、9007199254740993、NULL 精确 |
| Parquet map/struct/list → JSON | 对应用例通过 | 已有支持，不应误报缺失 |
| Arrow utf8→ENUM/SET/UUID/vector/GEOMETRY | 不支持相关直接转换 | 特殊类型按文本/原生转换契约适配 |
| Parquet / Arrow WKT→GEOMETRY SRID4326 | 直接拒绝 | WKB binary→VARBINARY 暂存→ST_GeomFromWKB(...,4326)，字节与 SRID 精确 |
| Arrow dictionary categorical→VARCHAR | 中文、空值、NULL、重复值通过 | 保留已支持能力 |
| Arrow timezone-aware timestamp→TIMESTAMP | instant 对照通过 | 不是缺失项 |

DECIMAL76 DDL 明确不支持（数据库最大精度65），不请求把这个 DDL 限制当成 Arrow 错误。

## 可复现 fixture 与导入过程

依赖 PyMySQL 1.2.3 / pyarrow 26.0.0。'''+PRE+'```python\n'+CONN+'''import pyarrow as pa
from decimal import Decimal
fixtures=[
 ('dec65','DECIMAL(65,30)',pa.decimal256(65,30),
  [Decimal('9'*35+'.'+'9'*30),Decimal('-'+'9'*35+'.'+'9'*30),None]),
 ('map_json','JSON',pa.map_(pa.string(),pa.int64()),
  [[('中文',9007199254740993),('empty',0)],None]),
 ('wkt','GEOMETRY SRID 4326',pa.string(),['POINT(1.25 -2.5)',None])]
for name,ddl,ty,vals in fixtures:
    t=pa.table({'id':pa.array(range(1,len(vals)+1),pa.int32()),'v':pa.array(vals,ty)})
    p=root/(name+'.arrow')
    with pa.OSFile(str(p),'wb') as f:
        with pa.ipc.new_file(f,t.schema) as w:w.write_table(t)
    c.execute('DROP TABLE IF EXISTS '+name)
    c.execute(f'CREATE TABLE {name}(id INT PRIMARY KEY,v {ddl})')
    try:c.execute(f"LOAD DATA INFILE {{'filepath'='{p}','format'='arrow'}} INTO TABLE {name}")
    except pymysql.MySQLError as e:print(name,str(t.schema),str(e))
    c.execute('SELECT COUNT(*) FROM '+name);print('rows after error',c.fetchone())
d.close()
```

## 实现建议与验收

- [ ] 明确 strict exact-layout 与 opt-in conversion 的边界；支持矩阵写清 source physical/logical type、target type、precision/scale、NULL 和错误行为。
- [ ] Decimal256 最高65位精确、禁止 float 中转；不支持的76位或 rescale 按明确规则拒绝。
- [ ] nested JSON 保留大整数、空容器、NULL、Unicode；定义 map key 和重复 key 规则。
- [ ] 特殊类型通过显式转换 profile，geometry 指定 SRID 并使用已记录的 WKB 协议，避免猜测 per-value SRID。
- [ ] conversion 错误可定位字段/行，不留下半批数据；dictionary、timestamps 和已有 zero-copy 路径保留回归。

## 关联
'''+links([(23684,'原 Arrow 静态文件 feature；本请求扩展其明确有限范围：',False),(28590,'已修复 DECIMAL256 文本文件支持，本轮 CSV/JSONLINE/Parquet 的 DECIMAL65 对照通过：',False),(25473,'decimal scale 的历史正确性问题，应纳入转换回归：',False),(27746,'生态类型认证背景：',False)])+'''

原始 receipt：`advanced-matrix-result.json`、`semantic-matrix-result.json`、`complex-types-result.json`、`final-adaptations-result.json`。
''',kind='feature')

add('ibis_metadata','[Compatibility]: Ibis MySQL backend maps BIGINT UNSIGNED(64) metadata to unknown instead of uint64',ENV+'''## 现象与归属

Ibis 12.0.0 MySQL backend 对 MatrixOne 普通 BIGINT UNSIGNED 列的 schema 为：

```text
large_unsigned unknown(DataType(this=DType.USERDEFINED, kind=BIGINT UNSIGNED(64)))
```

同样表/客户端连接真实 MySQL 8.4，schema 为 uint64。建议 P1：标准 MySQL 生态的类型发现不兼容。

与执行端的精度问题分开：同一 Ibis 默认 execute 将 nullable integer / decimal 转 float 的损失，在 MO/MySQL 两端都出现；那部分不能据此归因 MatrixOne 内核。本 issue 只跟踪 unsigned 类型元数据识别。

## 完整复现与过程

依赖 `ibis-framework[mysql]==12.0.0`、PyMySQL1.2.3。先创建含 signed/unsigned/decimal/null 的表，再用 Ibis .table(...).schema() 发现类型；记录 SHOW FULL COLUMNS / information_schema 与客户端版本。下面是从已运行宽表裁剪的重跑脚本，裁剪版本身尚未另行执行；原宽表已运行并保存 schema。

```python
import os,pymysql,ibis
host=os.getenv('MO_HOST','127.0.0.1');port=int(os.getenv('MO_PORT','6001'))
user=os.getenv('MO_USER','root');pw=os.environ['MO_PASSWORD']
with pymysql.connect(host=host,port=port,user=user,password=pw,autocommit=True) as d:
    with d.cursor() as c:
        c.execute('CREATE DATABASE IF NOT EXISTS ecosystem_issue_repro')
        c.execute('USE ecosystem_issue_repro')
        c.execute('DROP TABLE IF EXISTS unsigned_meta')
        c.execute('CREATE TABLE unsigned_meta(id BIGINT PRIMARY KEY,s BIGINT,u BIGINT UNSIGNED,d DECIMAL(38,18))')
        c.execute("INSERT INTO unsigned_meta VALUES(1,9007199254740993,18446744073709551615,'12345678901234567890.123456789012345678'),(2,NULL,NULL,NULL)")
        c.execute('SHOW FULL COLUMNS FROM unsigned_meta');print(c.fetchall())
        c.execute("SELECT column_name,data_type,column_type FROM information_schema.columns WHERE table_schema='ecosystem_issue_repro' AND table_name='unsigned_meta'")
        print(c.fetchall())
con=ibis.mysql.connect(host=host,port=port,user=user,password=pw,database='ecosystem_issue_repro')
try: print(ibis.__version__,con.table('unsigned_meta').schema())
finally:con.disconnect()
```

用同一脚本连接真实 MySQL（改 endpoint/密码）作为 metadata 对照；不要仅用 float dataframe 判断 uint64 精度。原始执行控制：CAST 大整数与 decimal 为 CHAR 后，int/Decimal 重建精确，两端均通过。

## 预期、定位与验收

- [ ] 面向 MySQL client 的整数元数据使用能被标准生态解析的 COLUMN_TYPE/SHOW 类型表达，或提供明确的 Ibis MO adapter；不得丢 unsigned 标志。
- [ ] 验证所有 integer widths、signed/unsigned、普通列/表达式列、nullable/NOT NULL；unsigned64 必须 schema 为 uint64 或明确支持的等价类型。
- [ ] BIGINT UNSIGNED 最大值、NULL 不经 float 比对；metadata 修正不能破坏 DECIMAL/BIT/VARCHAR 长度。
- [ ] Ibis upstream parser 和 MO metadata 分别定位，记录具体元数据查询与返回值，避免无证据宣称协议字段已错。

本轮没有对相关元数据代码做最新 main whole-file parity 核对。

## 关联与区别
'''+links([(28819,'已关闭的内部宽度零显示为 UNSIGNED(0) 问题；这里是 UNSIGNED(64) 被 Ibis parser 识别为 unknown，不能直接算已修复：',False),(26680,'ODBC DATA_TYPE 大小写的历史问题，另一个元数据契约缺陷：',False),(26677,'ODBC 元数据认证背景：',False),(27746,'MySQL 生态兼容性认证背景：',False)])+'''

原始 receipt：`tool-controls-result.json` 中 MO/MySQL ibis_default_observation；`dataframe-readers-result.json` 保存 Ibis/ConnectorX 版本。
''')

add('s3_txn','[Feature Request]: Transactional publish and recovery contract for writable S3 external tables',ENV+'''## 请求与现有设计

为 raw S3 writable external tables 定义可选择的 commit-aware publish / recoverable outbox 协议，或显式禁止用户把此类写入误认为与原生表原子提交。优先级建议 P1；若产品承诺跨湖/库原子事务，应升级处理。

PR #24889 明确写入不参与事务，这里是增强请求，**不是认定原生事务引擎违反现有 ACID 承诺**。raw writable external table 与 Iceberg table commit 是不同路径。

## 已运行的测试条件和过程

同一 MatrixOne 实例，真实本地 MinIO S3-compatible service，boto3 1.43.106。writer 与 observer 为两个独立 SQL 连接，原生表作为事务隔离控制；测试 prefix 在开始前为空。

1. 创建 S3 STAGE、原生控制表、带 `%U` write_file_pattern 的 writable external table。
2. writer BEGIN，先 INSERT 原生控制表，再 INSERT 外表。
3. 不结束 writer 事务，observer 读取原生表与外表；boto3 LIST object 并 GET 内容。
4. JSONLINE 用例执行 ROLLBACK；CSV 用例直接关闭 writer 连接。
5. observer 再读两个表；再次 LIST/GET 对象。

| 分支 | commit 前原生行数 | commit 前外表 | rollback/断连后原生 | rollback/断连后外表 |
|---|---:|---|---:|---|
| JSONLINE / explicit rollback | 0 | 可读 uncommitted 行，S3 对象已存在 | 0 | 行和对象仍在 |
| CSV / connection close | 0 | 可读 uncommitted 行，S3 对象已存在 | 0 | 行和对象仍在 |

原始 JSON 对象内容：`{"id":1,"name":"external uncommitted"}`；CSV：`1,"external uncommitted"`。测试断言按“跨存储原子可见性”的目标失败，**按当前明确非事务设计，这是已知能力边界**。

## SQL 重跑步骤

用可丢弃的 S3 bucket/prefix 和两个 SQL session。下方凭据占位符替换为临时服务配置，不要公开真实凭据； endpoint 需 MatrixOne 服务端可达。

```sql
CREATE DATABASE IF NOT EXISTS external_txn_repro;
USE external_txn_repro;
CREATE STAGE txn_stage URL='s3://<bucket>/txn-repro/'
CREDENTIALS={'aws_key_id'='<temporary-key>','aws_secret_key'='<temporary-secret>',
 'aws_region'='us-east-1','endpoint'='http://<minio-host>:9000','provider'='minio'};
CREATE TABLE txn_control(id BIGINT PRIMARY KEY,name VARCHAR(100));
CREATE EXTERNAL TABLE txn_external(id BIGINT,name VARCHAR(100)) INFILE {
 'filepath'='stage://txn_stage/json_*.dat','format'='jsonline','jsondata'='object',
 'write_file_pattern'='stage://txn_stage/json_%U.dat'};
-- session A
BEGIN;
INSERT INTO txn_control VALUES(1,'native uncommitted');
INSERT INTO txn_external VALUES(1,'external uncommitted');
-- session B, after last INSERT returns, before COMMIT/ROLLBACK
SELECT * FROM txn_control;
SELECT * FROM txn_external;
-- use S3 LIST prefix txn-repro/, GET object bytes
-- session A
ROLLBACK;
-- session B repeat both SELECT and S3 LIST/GET
```

另建 CSV 外表（format=csv，FIELDS TERMINATED BY ','），重复步骤并以 writer connection.close() 替代 rollback。上述两个原分支均已运行。

## 实现选项与验收

- [ ] 给出 explicit autocommit external-write 与 transactional publish 两种清晰契约；若不能参与事务，在 BEGIN 内明确拒绝/诊断。
- [ ] 事务模式使用不可见 staging object + transaction/manifest commit publish，或 durable outbox；需要定义物理 LIST 可见性与通过外表读的逻辑可见性，不能混为一谈。
- [ ] commit 前其他 SQL 连接不读取未提交行；rollback/断连不发布数据；保留 staging 垃圾也必须可追踪回收。
- [ ] 提交确认丢失、进程重启、对象已上传但 metadata 未提交、重复任务重放均可恢复，明确去重键和 retry 行为。
- [ ] 分别验证 raw external 与 Iceberg；发布 exactly-once 声明前需要系统故障矩阵，本轮未认证。

## 关联
'''+links([(24889,'明确非事务限制的 writable external table 实现：',True),(27517,'外表 reject accounting 与错误可观测性，可组合但不能代替提交协议：',False),(27746,'跨系统恢复/一致性认证背景：',False)])+'''

原始 receipt：`s3-transaction-deep-result.json`（2 个分支及对象内容）。
''',kind='feature')

add('ecosystem','[Test]: Qualify lossless ecosystem adapters and full Airbyte/NiFi/Kafka Connect recovery pipelines',ENV+'''## 目标与范围

将“能连上 MySQL 协议”提升为可重复的类型、变更与恢复认证：发布各工具 connector profile、必要适配 SQL、版本支持矩阵和错误行为。新增 full runtime Airbyte、NiFi、Kafka Connect 优先验证删除传播、schema evolution、checkpoint/restart 和逐字段保真。

**本轮尚未运行这三者的完整环境**；此 issue 是测试/适配任务，不能用已有 Spark/DataX/SeaTunnel/Singer 结果替代它们的认证，也不把上游工具固有限制全报成数据库内核 bug。

## 已运行基线与控制

统一人工宽表：signed64 的 9007199254740993 / INT64_MIN；unsigned64 的 UINT64_MAX / 0；DECIMAL(38,18) 的 `12345678901234567890.123456789012345678`，DECIMAL(65,30) 的35位整数+30位小数正负边界；binary `00ff80616263` / 空bytes / NULL；中文+emoji；DATETIME6 微秒；含大整数的 JSON / [] / NULL。

| 工具 | 已运行结果 | 归属/限制 |
|---|---|---|
| SeaTunnel 2.3.12 JDBC | 6项完成：MO→MO、真实MySQL→MO、更新新增、主键upsert重放、新列未适配拒绝、适配后恢复 | is_exactly_once=false；仅证明 at-least-once 主键收敛，不证明删除传播 |
| pipelinewise-tap-mysql 1.6.0 | 6项适配 snapshot/cursor incremental/resume 对照完成 | Singer messages 源路径，未运行 community target、未证明 binlog CDC/删除 |
| DataX bundled Connector/J5.1.47 | 4项宽类型 MO/MySQL→MO 完成 | temporal text stage 后原生类型还原；未认证 change/delete |
| Spark 3.5.7 JDBC | Decimal65 原生 schema 两端失败；CAST Decimal65 AS CHAR 后读写两端精确 | Spark Decimal 最大精度38，为上游边界 |
| ConnectorX0.4.6 | 两端直接读 decimal 都有 scale mismatch；CAST decimal AS CHAR 后精确 | 非 MO 独有；保留原始和适配路径 |
| Ibis12.0.0 | 默认浮点转换两端均丢大整数/decimal；text adaptation两端精确 | MO unsigned metadata unknown 是另立的兼容缺陷 |
| pandas3.0.6 / Arrow26 | coerce_float=False 保留 nullable signed/unsigned；Decimal变为精确字符串；raw binary两端有UTF8解码错误，HEX envelope后精确 | 类型变成string不等于数值损失；须记录dtype与内容 |

## 基线重跑方法

1. 在同版本 MO 和真实 MySQL 创建一致表和上述固定数据，记录 server/client/JDK/connector 版本、SQL mode、time zone。
2. 原始路径先跑，记录原错误和schema；再跑显式适配路径，不用适配成功掩盖原失败。
3. 数值与 binary 对照必须离开 float 路径：int/Decimal/bytes 精确比较；JSON语义比较同时保留原文；NULL/empty分开；timestamp同时比较instant和微秒。
4. 示例 adapter：`CAST(d65 AS CHAR)`；Python读取大整数/decimal时显式 text envelope并 int/Decimal重建；binary用HEX/UNHEX；需要的 temporal/text staging在写入MO后CAST回目标类型。
5. 记录源/目标总行数、主键集合、每字段值、重复数、reject数、checkpoint位置，不能只看进程退出码。

## 下一阶段 full-runtime 验收矩阵

- [ ] Airbyte：实际 source→worker→destination write，保存 catalog/state/日志；full refresh、cursor incremental和真正CDC模式分别标注。
- [ ] NiFi：实际 flow与controller service / JDBC driver；ExecuteSQLRecord/QueryDatabaseTableRecord与PutDatabaseRecord或明确CDC消费路径，保存flow和队列状态。
- [ ] Kafka Connect：实际worker + source connector + broker + sink connector；source CDC delete/tombstone到MO删除，明确converter/schema registry与主键模式。
- [ ] 对每条链路运行 snapshot、insert/update/delete、NULL↔empty、大整数/decimal/binary/Unicode/微秒、增加nullable列、类型变更、重命名/删除列的支持/拒绝行为。
- [ ] 处理中断worker/connector、checkpoint后断连、批次部分写入后的retry、重启恢复；对比源目标PK和值，并统计重放重复或漏行。
- [ ] 删除传播须证明物理删除或明确的soft-delete contract；cursor扫描不能冒充删除CDC。
- [ ] Airbyte/NiFi/Kafka Connect完整链路通过不自动等于吞吐/长稳/跨系统exactly-once；这些需独立计划和故障注入证据。

## 与已有任务挂接
'''+links([(27746,'既有 Flink qualification：复用对照方法，但新工具独立验收：',False),(26677,'既有 first-class ODBC资格认证：共享 metadata/Unicode/null契约：',False),(28174,'既有SQL/PGQ图能力规划：后续图数据导入与边/点删除适配依赖该能力，未声称已实现图引擎：',False),(23684,'Arrow静态文件有限支持范围：',False),(28819,'整数metadata历史问题：',False),(25658,'历史CDC消费启动但MO无行的问题，可作为链路观测/诊断背景，不认定同根因：',False)])+'''

原始 receipt：`expanded-audit-summary.json`、`seatunnel-result.json`、`singer-result.json`、`legacy-wide-tools-result.json`、`tool-controls-result.json`、`semantic-retest-result.json`。新增 full-runtime 结果需记录实际版本/路径/故障，不能复制基线PASS状态。
''',kind='feature')

for item in issues:
    item['body']=item['body'].replace("OPTIONALLY ENCLOSED BY '\"'\"", "OPTIONALLY ENCLOSED BY \"+repr(chr(34))")
    item['body']=item['body'].replace("'\\N'", "chr(92)+'N'")
(B/'new-issue-drafts.json').write_text(json.dumps(issues,ensure_ascii=False,indent=2))
print(json.dumps([{'key':i['key'],'title':i['title'],'chars':len(i['body'])} for i in issues],ensure_ascii=False,indent=2))
