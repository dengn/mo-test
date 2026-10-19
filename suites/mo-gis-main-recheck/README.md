# 当前 main GIS 问题复核与应用可用性

复核日期：**2026-10-13，北京时间**。测试、提交 issue 时 GitHub `main` 均为 `0a4db0e6a6517e489a333ad9073dfcdc5d26aff4`。从该提交重新编译，使用全新数据目录及 SQL6012/HAKeeper33011 独立实例，运行时 `git_version()` 为 `0a4db0e`。原有 6011、旧 6001 数据均未重置。

## 复核结果

| 现象 | 当前 main | 英文 issue |
| --- | --- | --- |
| 有效多边形共边/共角的 ST_Intersection 丢失 LINESTRING/POINT，返回 POLYGON EMPTY | 常量与存储路径均复现 | [#30032](https://github.com/matrixorigin/matrixone/issues/30032) |
| 相邻重复顶点的有效 LineString 被 ST_IsValid 判为无效 | 常量与存储路径均复现 | [#30033](https://github.com/matrixorigin/matrixone/issues/30033) |
| 未闭合、仅三位置的 polygon 被接纳、存储，输出的 WKB 无法独立解码 | 常量、存储与独立 Shapely 解码均复现 | [#30034](https://github.com/matrixorigin/matrixone/issues/30034) |

9 个常量查询 × MO/PostGIS/MySQL 三端 × 各 3 轮 = **81 次实际查询**，另有 **4 个 MO 存储输入接纳记录 + 4 个存储查询**，共 **89 条主复核记录**。正常闭合多边形、无重复线和面积相交 0.5 的控制，三端均 3/3 正确。这些记录独立于原有 600,000 主用例及 13,925 GIS 差分用例，不增加其数量。

对照版本是 PostgreSQL18.6/PostGIS3.6.4、MySQL8.0.46。每次复核的输出在 [recheck-results.json](recheck-results.json)；版本及 binary SHA-256 在 [versions.json](versions.json)。完整三份英文 issue 正文和 [submitted-issues.json](submitted-issues.json) 均保留。提交前检索了相关函数名、输入和已知 SRID/叠加问题，没有找到同一复现的已有 issue；没有提交 PostGIS 异常或将功能缺口当作这三类 bug。

## GIS 类应用能否使用 MO

**可以用于明确验证过的业务 GIS 场景。** 上一轮已实测 OpenLayers 地图和 HTTP 增删改查、围栏、附近点、空间连接、WKB/GeoJSON 交换、事务及故障恢复，见 [完整对比报告](../mo-gis-postgis/REPORT.md)。本轮新 main 再次实测米制距离约 140.140936 米、200 米附近点、围栏返回、GeoJSON、事务回滚及平面空间索引，全部通过，[application-acceptance.json](application-acceptance.json) 保存实际输出与 EXPLAIN。

使用边界应按查询类别区分：

| 应用需求 | 已验证范围/当前限制 |
| --- | --- |
| 点位、路线、围栏、业务属性、GeoJSON 地图展示 | 可实现；OpenLayers 最小项目已实测，不能推断其他框架自动兼容 |
| 经纬度米制距离/附近检索 | 显式 SRID4326 的量测和筛选正确；计算定义为球面，与默认椭球 PostGIS 有差异 |
| 平面空间索引 | 本轮 EXPLAIN 为 Index Table Scan，结果正确 |
| **SRID4326 空间索引加速** | **优化器主动禁止下推，当前查询走 Table Scan**。为避免跨日界线/大圆边包围盒漏查，待索引键能覆盖相应范围后才能安全启用；不能凭成功建索引推断经纬度过滤已经受益 |
| 大规模经纬度在线检索 | 本轮功能成功不证明吞吐或延迟；需结合上述扫描限制设计分区/网格候选筛选并针对数据量验证 |
| GeoDjango | 5.2 已验证的适配要求显式建列/写入 SRID、两参 GeoJSON及部分原生 SQL；6.1 原生 MySQL backend 的版本门槛仍有障碍 |
| 坐标变换、复杂几何修复、3D/M、栅格、瓦片及持久拓扑 | 此前探测到缺口或未证明 MO 原生可实现；可在 ETL/应用层或配合 PostGIS 完成，不能当作 PostGIS 直接替换 |
| 接触边界叠加、几何有效性与导入 | 上述 3 类问题仍存在，应避免依赖受影响行为，并在接入前做结构校验 |

SRID4326 限制的源码依据：[findSpatialIndexFilter](https://github.com/matrixorigin/matrixone/blob/0a4db0e6a6517e489a333ad9073dfcdc5d26aff4/pkg/sql/plan/apply_indices.go#L164)。这是明确的正确性保护，不作为错误结果 bug 提交。之前的平面索引验证不能推广为 geodetic 索引加速。

## 方法及保留的工具错误

首轮记录写出时遇到 build_version 的 datetime JSON 序列化错误，修正归一化后重跑。第二轮应用断言错误地预期 SRID4326 使用索引；实际计划和源码揭示上述保护限制，因此保留该失败，并改为分别验证“geodetic 扫描”与“planar 索引”的真实承诺。最终轮所有主记录写出、正常控制和应用验收均成功。两份失败日志及第二轮原始 bug 记录都保留，未计作额外成功用例或产品 bug。

脚本 `recheck.py` 会在本套件自己的 `gis_main_verification` 数据库重建 `repro_geoms`、`app_places`、`app_planar` 三张测试表；只适用于独立测试实例。PG/MySQL 对照仅执行 SELECT，不改写其数据。`start-main.sh` 的源码/二进制/配置路径为本环境已验证路径，其他机器须调整。数据库、进程 PID、二进制及构建缓存不上传。

源码未修改以修复产品问题；本轮只复核和报告。问题的提交不代表已经修复，也不表示此前所有 GIS 用例在新版本上重新全量执行。正式 GIS 日志没有观察到未捕获 panic。
