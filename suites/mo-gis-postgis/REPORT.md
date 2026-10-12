# MatrixOne GIS 功能与 PostGIS 对比实测

测试日期：2026-10-12；正式负载使用独立 MO 实例 `127.0.0.1:6011`。MO 已具备原生 GIS 类型，能完成围栏、附近点、空间连接、地图展示和带几何数据的事务应用。本轮确认 **3 类 MO 正确性问题**；同时记录了功能缺口、API/数值定义差异及一项 PostGIS 球面面积异常。正式 GIS 工作负载未观察到未捕获 panic，强杀恢复没有丢失已确认提交的数据。

这是一份当前 MO GIS 表面的系统功能测试及应用样例对比。130 个已注册名字均有执行记录，但不表示所有参数组合、所有 PostGIS 函数或所有 GIS 项目已经穷尽。原始失败、工具配置失误和修正后的复测全部保留。

## 引入时间与版本

**main 首次可用的原生 GIS 类型于 2026-04-15 合入 #24136**；3.0-dev 于 2026-05-08 补齐，普通发行版 v3.0.12 已包含；WKB、GEOMETRY32、S2 球面引擎于北京时间 2026-06-09 合入 #24777。具体代码、标签和日期见 [HISTORY.md](HISTORY.md)。

| 项目 | 本次实际版本 |
| --- | --- |
| MatrixOne | main `f1fc3f944e0835af83115675ea18c950be2c2937`，本地源码编译；协议版本串仍为 `8.0.30-MatrixOne-v1.3.0`，以 git hash 为准 |
| PostgreSQL / PostGIS | 18.6 / 3.6.4 `94d984b` |
| 几何/坐标引擎 | GEOS 3.14.1，PROJ 9.8.1，GDAL 3.10.3；启用 PostGIS raster/topology |
| 官方 MO SQL runner | matrixorigin/mo-tester `309a0ca650e0c55e90292767fd61e4976818d66d` |
| 独立判定工具 | Shapely 2.2.0、Pyproj 3.8.0、h3 4.5.0、s2sphere 0.2.5 |
| 项目集成 | OpenLayers 10.11.0 + Chromium；GeoDjango 6.1.2 和 5.2.18 |

PostGIS 原始镜像 digest 为 `sha256:60f6ad1d21ea86a67d47780b9a0d1e1d200500f62b19293fa834d0dea80b8677`。Docker VFS 多层展开占用了约 8 GB，因此将自己的容器文件系统 export/import 成单层镜像，再重建测试数据库后才运行正式对比。二进制和版本保持原样；[versions.json](versions.json)、`postgis-flatten.log` 保存来源。未删除其他任务的容器。

## 执行范围和计数

| 测试层 | 已完成 | 结果 |
| --- | ---: | --- |
| 主差分用例 | 13,815 | 13,207 直接一致，500 MO 扩展检查，11 双端预期拒绝；其余保留并逐条归类 |
| 32 位几何、球面和补充接口 | 110 | 56 直接一致，20 MO 扩展检查；发现 21 个 GEOMETRY32 缺失重载样例及其他差异 |
| 原生类型/建表/约束/索引 smoke | 106 | 97 成功，9 预期拒绝；18 个类型与别名 |
| 官方 `cases/geo` BVT | 795 | 795 成功，0 失败/忽略/异常 |
| 官方 `func_geometry.test` BVT | 787 | 787 成功，0 失败/忽略/异常 |
| `go test -count=1 -json ./pkg/geo/...` | 416 测试与子测试事件 | 全部成功，0 失败/跳过；另有 1 个 package pass 事件 |
| 数据库应用工作流 | 9 类 | 修正测试判定/SQL 后均通过；原始 12 条执行记录含 3 条工具侧错误 |
| 浏览器、HTTP、ORM | 真实最小项目 | OpenLayers 双端通过；GeoDjango 原生兼容性限制及有效适配分别实测 |
| SIGKILL 后同目录恢复 | MO、PG 各 1 次 | 已确认提交均保留，几何值和空间索引计数正确 |

13,925 条差分用例有唯一 ID，case/result 集合完全对应，`triage.py` 已校验无缺失、无重复、无未归类。名字覆盖为 **130/130，106 个 canonical function ID**，详见 [mo-function-matrix.csv](mo-function-matrix.csv)。名字覆盖包括别名及少量输入的可用性探测，不等同于所有重载覆盖。

PostGIS 已安装扩展的函数签名清单和逐签名覆盖说明保存在 [postgis-catalog-matrix.csv](postgis-catalog-matrix.csv)。标记 `catalogued_not_exhaustively_executed` 的接口没有被穷尽实测；标记 `sampled_by_name_not_all_overloads` 也不能解释为该名称所有重载均通过。SFCGAL、Tiger 未启用或实测。

差分用例包含全部几何家族、空几何、洞、多对象、嵌套集合、列向量与常量、typed NULL、WKT/WKB/GeoJSON、SRID、平面量测、关系谓词、MBR、叠加、缓冲、凸包、简化、线性参照、S2/H3，以及异常编码、非有限坐标、深度与点数预算。800 组固定种子矩形使用解析面积和 Shapely 作独立判定，包含相离、重叠、包含、边接触及角接触。主批次多数是小型函数查询，执行约 11.75 秒；不据此宣称长时间稳定性或极端吞吐。

官方 BVT 使用 `-n`，仅不比较结果集元数据，仍比较数据结果及预期错误；没有重生成 golden。本轮类型/DDL 元数据另有 smoke，协议所有元数据组合仍未穷尽。CSV 原生 `LOAD DATA INLINE`、文件导入及 external table 已在 `geo_load.sql` 的 26 条官方检查中执行；应用 CSV 交换部分通过客户端导入，应分开解读。

## 确认的 MO 正确性问题

以下按可复现行为归并为 3 类，不能把原始几十条 difference/error 当作几十个 bug。每类均在恢复后的新连接重复验证；24 条复查记录在 [findings-repeatability.json](findings-repeatability.json)。英文 issue 草稿在 `findings/`，本轮尚未对外提交。

| 编号 | 最小输入及 MO 行为 | 对照与应用影响 |
| --- | --- | --- |
| MO-GIS-001 | 两个有效多边形共边/共角，`ST_Intersection` 返回 `POLYGON EMPTY` | PostGIS 返回 LINESTRING/POINT；共边 MySQL 控制也返回 LINESTRING。边界相交丢失，影响邻接、道路/地块边界处理；7 条主批次样例归于该类 |
| MO-GIS-002 | `ST_IsValid(ST_GeomFromText('LINESTRING(0 0,0 0,1 0,1 0)'))` 返回 0 | PostGIS true、MySQL 1、Shapely true；重复相邻点不应让有长度的线无效，影响数据准入；2 条列/常量样例 |
| MO-GIS-003 | 接受 `POLYGON((0 0,1 0,1 1))`，输出未闭合的三点 ring | PostGIS 和 MySQL 拒绝；MO 输出的 WKB 无法被 Shapely 读取，GeoJSON polygon ring 也违反闭合且至少四点要求；属于输入结构校验与互操作问题 |

对照原始证据：[boundary-intersection-controls.json](boundary-intersection-controls.json)、[validity-and-ring-controls.json](validity-and-ring-controls.json)、[minimal-findings.json](minimal-findings.json)。另有极小 polygon 的 `ST_IsSimple` 2 条数值稳健性候选，尚未归入确认 bug。

## 能力与语义比较

| 场景 | MatrixOne 当前测试结果 | PostGIS 当前测试结果/迁移方式 |
| --- | --- | --- |
| 几何类型 | GEOMETRY、POINT/LINESTRING/POLYGON、MULTI、COLLECTION 及 32 位家族、GEOGRAPHY 共 18 种写法通过 smoke | geometry/geography 及多种高级类型；没有 MO 的 GEOMETRY32 同名类型 |
| WKT、标准 WKB、GeoJSON | 基础输入输出、跨端 WKB 交换通过；空 POINT 的合法 NaN 位模式可不同 | 可互操作；比较几何语义，避免用文本空格/字节完全一致替代几何判定 |
| SRID | 元数据、明确 SRID 输入可用；SRID 4326 走球面计算；现有无 SRID POINT 改成 SRID 4326 的 ALTER 被拒绝 | 列约束/值携带 SRID；默认 geography 量测为椭球，需 `false` 显式球面参照 |
| 坐标变换 | `ST_Transform` 未支持；设置 SRID 不变换坐标 | `ST_Transform` 实际变换坐标；MO 应在 ETL/应用中用 PROJ/Pyproj 变换后入库 |
| 附近检索 | `ST_Distance <= r` + 排序通过；可用空间索引谓词路径 | `ST_DWithin`、GiST、KNN 等接口更丰富；本轮仅验证所列 SQL，未作 KNN 性能比较 |
| 空间索引 | SPATIAL INDEX 建立/维护/回滚、EXPLAIN 索引路径与同数据全扫描结果通过 | GiST 对照通过；没有据此宣称两种索引性能相同 |
| 叠加分析 | polygon/multipolygon 面积叠加通过；边/点交集有上述 bug，line-polygon intersection 干净报不支持 | 支持多种维度组合；不能把该混合维度能力视为 MO 已具备 |
| GEOMETRY32 函数 | 多数基础读写/量测可用；10 个拓扑谓词、9 个 MBR 谓词、MakeEnvelope、GeoHash 的输入重载缺失 | 使用相同可精确表示的 fixture 作 geometry 控制；可显式升为 GEOMETRY 后调用，但不是原生 32 位重载 |
| 有效性 | ST_IsValid 对复合类型报不支持，重复顶点线有 bug；空/极小几何与 PG 定义有差异 | 复合几何判定、ST_MakeValid 等能力更完整；MO 未支持 ST_MakeValid |
| 全球 geodetic topology | 局部场景通过；跨日界线 polygon 与远端点的部分查询因无共同 gnomonic hemisphere 被拒绝 | geography 能返回该全球查询的 false；这是 MO 已文档化的运算域限制 |
| S2/H3 | 520 条扩展用例通过；ID 等关键输出用独立 Python 库控制 | 本轮基础 PostGIS 未安装对应扩展；不能记为 PostGIS 核心缺陷 |
| 高级格式/操作 | ST_AsGML、ST_AsKML、TWKB、encoded polyline、Subdivide、SnapToGrid、Segmentize、Relate 等已探测到缺口 | 对应控制 SQL 通过；KML/polyline 最初参考 SRID 配错，已用 4326 补测 |
| GeoJSON options | 1/2 参数可用，第三个 options 参数未支持 | GeoDjango 默认三参调用受影响；两参适配可用 |
| 3D/M | 本轮 Z/M constructor 及 ST_3DDistance 不支持 | Z/M 几何和 3D 距离控制通过 |
| 聚类、瓦片、栅格、持久拓扑 | 未证明原生支持这些 PostGIS 项目能力 | DBSCAN 100 行、100 要素 MVT、2×2 raster 像素值、CreateTopology 实际成功；不是仅阅读文档 |

空几何 `ST_Dimension`、`ST_NumGeometries`、`ST_IsValid` 产生 34 条语义差异，合法空 POINT WKB NaN 编码产生 4 条字节差异。重复顶点线的 `ST_IsSimple` 与 MySQL 相同而与 PG 不同；极小 polygon 的 `ST_IsValid` 也与 MySQL 相同。这些均未自动算作 MO bug。全部计数见 [summary.json](summary.json)，逐条决定见 [classified-results.jsonl](classified-results.jsonl)，原始记录未改写。

## 独立发现的 PostGIS 球面面积异常

`ST_Area(ST_GeomFromText('POLYGON((0 0,1 0,1 1,0 1,0 0))',4326)::geography,false)` 在此 PostGIS 3.6.4 返回 **12,281,281,066.690842 m²**；MO 返回 **12,364,031,909.46562 m²**，独立 Pyproj 等轴球面为 **12,364,031,909.465616 m²**，MO 与真正球面相符。

3 个不同纬度多边形均可复现。PostGIS 3.6.4 源码的 geography_area 在 `false` 路径仅设置 `s.a = s.b = s.radius`，没有清零 `s.f`；PROJ 的面积路径又用 `geod_init(..., spheroid->a, spheroid->f)`。独立 Pyproj 用平均半径加残留 WGS84 扁率重算，与该错误输出相差约微平方米量级。椭球模式则与独立 WGS84 椭球正确一致。证据在 [geodetic-area-controls.json](geodetic-area-controls.json)、[postgis-stale-flattening-controls.json](postgis-stale-flattening-controls.json) 及固定 3.6.4 tag 的 C 文件快照。此项应单独报告参考端异常，不算 MO 面积错误，也不推广成所有 PostGIS 版本都受影响。

## 实际应用项目

双端数据库各有 4,096 个固定网格点、路线、围栏、JSON 属性及可编辑几何。9 类工作流的最终记录在 [application-final-results.json](application-final-results.json)：

- 围栏/边界策略与索引、全扫描互证：72 条查询；空间连接的两个 zone 各返回 361 个点。
- 附近点半径筛选、最近 25 个点：使用独立坐标判定；排序显式将距离转为 DECIMAL(30,12)，再按 ID 消除数值末位造成的同距顺序差异。
- 分区 union/intersection/difference/symmetric difference 面积分别为 700/100/300/600，路线插值结果正确。
- 12 个双向 WKB roundtrip，双端各 256 行 GeoJSON、256 行 CSV 客户端交换及独立解码。
- 空间索引 INSERT/UPDATE/DELETE、ROLLBACK 与 EXPLAIN；无脏读、commit/rollback、断开未提交连接回滚。
- 每端 32 条点轨迹交给 8 个并发 worker，每条轨迹执行 20 次独立事务提交，共 **640 次确认提交/端**；最终 32 行坐标和版本累计值正确。

OpenLayers 最小项目以实际 MO/PostGIS API 读取三个城市点，GeoJSON 转 EPSG:3857 后在 Chromium canvas 绘制；两端 feature ID、投影范围及页面均验证。HTTP 测了中文/引号字段的增删改、200 米附近检索、非法/NaN 坐标 400、每端 64 次并发 GET。[MO 页面截图](web/openlayers-mo.png)、[PG 页面截图](web/openlayers-pg.png)、[HTTP 记录](web/http-results.json)、[浏览器记录](web/browser-results.json) 可核查。

GeoDjango 原生兼容性需要分别看待：

- 6.1.2 原生 MySQL GIS backend 在 MO 报告 MySQL 8.0.30 时，因最低版本 8.4 门槛直接拒绝连接；PostGIS backend 通过。
- 5.2.18 原生 MO backend 能执行基本 CRUD/空间操作，但 `ST_AsGeoJSON(g,8,0)` 因缺少三参重载失败。
- Django MySQL GIS backend 默认建 POINT 列、写入构造器不携带此处所需的显式 SRID，经纬度 lookup 的部分距离接口要求度单位。只修改 GeoJSON 参数时，MO 曾返回 0.001414 度而 PG 返回约 140 米，不能当作米制等价通过。
- 最终工作适配在建表时使用 `point srid 4326`、写入 placeholder 为 `ST_GeomFromText(%s,4326)`，显式创建 SPATIAL INDEX，并在距离/Within 条件中显式构造 SRID 4326 几何、使用二参 GeoJSON。实际北京附近距离 **140.140936 m**，PG 球面控制 **140.140935 m**；CRUD、过滤、输出成功，见 [geodjango52-working-adapter.json](geodjango52-working-adapter.json)。这是明确的项目适配，不能宣称原生 GeoDjango 全兼容。

查阅了 osm2pgsql 官方手册作为迁移场景来源，但未运行 osm2pgsql、QGIS、GeoServer 或完整 OSM 导入；OpenLayers/GeoDjango 实测也只是可复现最小项目。

## 边界、故障恢复及资源限制

默认最多 65,536 个顶点；100,000 顶点请求干净拒绝。会话设置 `max_points_in_geometry=131072` 后，100,000 点线的长度正确为 99,999，[vertex-budget-recheck.json](vertex-budget-recheck.json) 保存复测。因此这是可配置保护，不是 65,536 的绝对存储上限。集合深度 65/128 被预算 64 拒绝；深度预算内通过。遵守用户“100 万别测了”，本轮没有百万列测试。

| 强杀恢复 | MO | PostgreSQL/PostGIS |
| --- | ---: | ---: |
| COMMIT 后获得客户端确认的行 | 119 | 394 |
| 连接中断导致提交状态不明的行 | 4 | 4 |
| 恢复后记录数 | 120 | 394 |
| 缺失已确认提交 / 已确认几何损坏 | 0 / 0 | 0 / 0 |
| 空间索引 count | 120 | 394 |

MO 多出的 1 行来自未确认提交，其事务可以已提交而客户端未收到结果，不能归为错误。恢复后原 4,096 点业务数据完整、HTTP/浏览器重新通过。首次可查询约 MO 33.84 秒、PG 1.05 秒，仅是这次启动诊断。外层 4 CPU/32 GiB，PG 容器 2 CPU/4 GiB，负载/启动实现不同；这些数值不是公平性能基准。

正式运行日志及强杀前归档中没有 `panic:`/`fatal error:`；没有 OOM kill。构建阶段 cgroup memory.max 计数增加，不宣称“没有内存上限压力”。没有多节点、断网分区或多次长期故障循环测试。

## 工具侧异常与当前环境状态

初次搭建新 LOG 服务时，我遗漏根级 Hakeeper client 地址，默认 32001 连接了旧 6001 测试集群，冲突 heartbeat 导致旧实例 `inconsistent replicas` panic。此记录还在旧 Raft WAL 中，旧实例重启仍遇到回放错误。**旧 `/workspace/mo-stress/data` 全部保留，6001 尚未恢复**；未删除或修改其数据/WAL。本轮所有正式 GIS 测试都在改用 33001 discovery 的独立 6011 集群中执行。该事故是我配置隔离错误，不能当作 GIS 负载触发的 panic；证据在 [setup-isolation-incident.json](setup-isolation-incident.json) 和三个压缩日志中。

mo-tester 默认初始化清理非内置测试数据库，首轮 BVT 因而删除了我的 GIS fixture 数据库，与补充测试/ORM启动重叠。修正 runner 的 builtin-db 保护名单并仅重建 MO fixtures 后复测通过，见 `bvt-reset-incident.json`。其他保留的工具侧错误包括初始重复 ST_AsText 包装、未类型化 NULL、WKT 空格比较、距离浮点 tie 判定、PostgreSQL ORDER BY alias 写法及 Django import；均未算作产品 bug。

一次 browser final 复查碰上主动 SIGKILL，30 秒超时小于 MO 此次恢复时间，记录保留；恢复后完整重跑通过。主差分的原始结果来自独立实例，未受到这些复查工具错误覆盖。

## 复现与产物

1. 使用固定 MO commit、相同配置启动独立服务；必须让 LOG/TN/CN 三份配置的根 `[hakeeper-client]` 都指向自己的 33001。`start-mo.sh` 是本环境已验证的启动脚本，源码/二进制路径需按新机器调整。
2. 按上述官方 digest 准备 PostgreSQL 18.6 / PostGIS 3.6.4，SQL 端口 65432；只操作本套件拥有的容器。使用报告配置的本地合成测试账号，避免连接生产服务。
3. 安装 `requirements.txt`；运行 `bootstrap.py`、`generate.py`、`run.py`、`supplement.py`、`types-smoke.py` 和 `apps.py`。bootstrap 创建本套件数据库和表，重复运行会因 geoms 已存在而报错；在复测前显式归档旧结果、使用新的独立数据库/PG schema，或仅重置自己的 fixtures。apps.py 会重建其自有业务表。应仅在测试实例上执行。
4. `run_cases` 会按 ID 跳过结果文件中已有的用例。真正重新执行须先将旧 results 文件移到一个新的归档路径，不能把零新增执行当作新的测试成功。生成器 seed 为 20261012。
5. 官方 BVT 用固定 mo-tester 和保存的 SQL/expected/resource 文件；先保护 fixture 数据库，按报告路径执行 geo 目录和 func_geometry.test。完整命令在 `bvt.log`、`bvt-legacy.log` 及官方文件归档说明中。
6. `web/` 内 `npm ci`、esbuild 构建后运行 server/http/browser 脚本；GeoDjango 两个版本分别安装运行。有效 MO 适配命令为 `GEO_DJANGO_ADAPTED=3 GEO_DJANGO_TABLE_SUFFIX=_fixed2 GEO_DJANGO_ENGINES=mo GEO_DJANGO_RESULTS=geodjango52-working-adapter.json python geodjango_project.py`，使用 Django 5.2.18 环境。
7. `fault_recovery.py` 会 SIGKILL 本套件自有 MO process/PostGIS container 并原目录重启，需核实脚本中的固定进程、容器和路径，只在独立测试服务上执行。
8. 运行 `triage.py` 校验覆盖、生成最终分类和功能矩阵。原始 case/result、校准/复查、应用源码、截图、官方 BVT 快照和元数据均发布；运行数据库、镜像 filesystem、依赖目录、venv、二进制与缓存不入库。

所有对外新问题目前只准备草稿；既有 issue 与 600,000 主批次的状态不因这批跟进用例改变。源码未作 GIS 产品修复。
