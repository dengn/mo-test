# MatrixOne GIS 支持引入时间

核查日期：2026-10-12。以下时间统一使用北京时间（UTC+8）。依据 GitHub PR 的 `merged_at`、实际代码差异，以及发布标签对应的源文件；PR 创建、关闭、合入和正式发布分别核实。

| 阶段 | 时间 | 证据和实际范围 |
| --- | --- | --- |
| 原生 GIS 类型首次合入 main | **2026-04-15 16:12:34** | [PR #24136](https://github.com/matrixorigin/matrixone/pull/24136)，commit `d23b1258e58e56b9fa948a297dfe8cbb5585fa80`。新增 `T_geometry = 67`，打通 GEOMETRY、POINT、LINESTRING、POLYGON、各 MULTI 类型和 GEOMETRYCOLLECTION 的 DDL、存取、函数、SRID、元数据和空间索引路径。初版几何载荷使用 WKT。 |
| 补齐 3.0-dev 分支 | **2026-05-08 18:35:20** | [PR #24204](https://github.com/matrixorigin/matrixone/pull/24204)，commit `f8655f18ae79a09c7a8e42b0c52de588b0d4dfc8`。这是 main 已有能力向旧开发分支的重新实现，不是 main 首次支持 GIS。后续 #24353、#24342 继续补齐类型校验等。 |
| 已核实包含原生 GEOMETRY 的普通 3.0 发布版 | **v3.0.12，2026-05-18 11:59:05 发布** | [v3.0.12](https://github.com/matrixorigin/matrixone/releases/tag/v3.0.12) 的 `types.go` 已有 `T_geometry`；前一个普通版本 v3.0.11 尚无。此判断针对普通版本序列，不声称穷尽每个 hotfix、内部构建和私有发行物。 |
| GIS 几何引擎重写 | **2026-06-09 06:53:26** | [PR #24777](https://github.com/matrixorigin/matrixone/pull/24777)，commit `024703548aca70dcbb49753f89daf4dd3cbfb99b`。WKT 存储改为 WKB；引入 GEOMETRY32、S2 球面长度/面积和更多空间函数。v4.0.0-rc2 尚无 GEOMETRY32，v4.0.0-rc3 已有。 |
| S2/H3 网格 SQL 函数 | **2026-06-27 02:21:01** | [PR #25065](https://github.com/matrixorigin/matrixone/pull/25065)，commit `905a92e88e2757a7971389d59073949515b6f77c`。独立的 S2/H3 cell/index 函数及别名。 |

首次合入的直接代码证据：[types.go 差异](https://github.com/matrixorigin/matrixone/commit/d23b1258e58e56b9fa948a297dfe8cbb5585fa80)。其直接父提交 `00337502100fb1f6e9fca412c691f64a6f218624` 没有 `T_geometry`；该提交新增原生类型及 planner 的 `MYSQL_TYPE_GEOMETRY` 映射。历史上解析器中出现过 GEOMETRY 语法或 MySQL 协议类型编号，不能据此认定已经支持可用的 GIS 数据类型。

容易混淆的 PR：#24135、#24198、#24890 均关闭而未合入；不能把它们的关闭日期用作支持上线时间。尤其 #24890 虽名为 GIS 引擎向 4.0-dev 的移植，`merged_at` 为 null。

原始 API、标签代码快照和父提交检查位于 [sources/history](sources/history/)。当前功能对比测试版本是 main `f1fc3f944e0835af83115675ea18c950be2c2937`；以上历史时间不代表所有函数、所有 GIS 应用或与 PostGIS 完全兼容从该日起就已具备。
