# 五个真实开源 GIS 应用与 MatrixOne 的兼容性测试

2026-10-13（北京时间）。本轮部署并运行 **GeoServer、pygeoapi、QGIS、uMap、Maputnik**，用真实应用的 SQL 驱动、HTTP API、地图渲染和浏览器交互测试 MO。每条报告结论都有输入、应用响应、数据库核验或图片证据。没有修改 MatrixOne 产品代码；需要的应用适配另存为源码。

MatrixOne 实测构建为 main `fa7cc1d9b38e3324572a4efc5617033522de0cbf`（SQL 6013），参考实例为 PostgreSQL 18.6/PostGIS 3.6.4（65432）与 MySQL 8.0.46（63306）。后来观察到 main 已推进至 `3e50e1b32d8da61bbbf70c89989fb08b671809de`；TTL、几何输出协议相关源码未改变，但不声称重建并运行了该新提交。

## 应用结果

|项目与版本|实际完整工作流|MO 原生接入的结果|可用接入路径|
|---|---|---|---|
|GeoServer 3.0.1 / GeoTools 35.1|REST 建库发布图层 → WFS 查询、bbox、属性过滤 → WMS PNG → WFS-T 插入/更新/删除并核验 SQL|读和渲染通过；WFS-T 插入、属性更新通过，删除触发 GeoTools 的动态 SRID setter，MO 拒绝|单独的 GeoTools SPI 适配只改 envelope SQL 后，五项工作流全部通过|
|pygeoapi 0.24.0|OGC API / Queryables / CQL2 → 259 点及全部几何家族 → 11 页无重无漏 → bbox → POST/PUT/DELETE → 8 并发混合读写|读取、分页、属性过滤和 CRUD 通过；原 MySQL provider 的 bbox 构造缺少 SRID，失败|小型 provider 子类显式指定 SRID，并用相交语义过滤 bbox；bbox、CRUD、混合负载通过|
|QGIS 3.40.6|载入真实 WFS 图层 → EPSG:3857 客户端投影绘图 → 保存 .qgz → 导出/重读 GeoPackage → 修改属性与几何 → 核验 SQL → 恢复|MySQL/OGR 直连能读行，却读不到几何：已提交 #30046|连接 GeoServer 的 MO 适配数据源；259 个几何、图片、工程、导出、几何和属性双向编辑通过|
|uMap 3.8.1 / Django 5.2.18|真实登录/CSRF → 建地图/点线面图层 → MO 实时 GeoJSON → 权限拒绝 → 分享/克隆 → .umap 导出 → 浏览器交互与中文弹窗|整个应用数据库无法直接替换为 MO：原生迁移遇到不兼容 DDL，应用本身依赖 Postgres 功能|**PostGIS 保存 uMap 元数据，MO 保存/提供地理业务数据**；实时 259 点和 3 个本地图形在浏览器工作。是混合部署|
|Maputnik v3.1.0 / MapLibre GL|实际样式编辑器读取 MO/PG 三类 GeoJSON → 点线面绘图 → UI 改半径/颜色 → 导出 JSON → 再导入验证|应用通过标准 GeoJSON 服务访问数据，不直接使用 SQL 驱动|MO → pygeoapi → Maputnik；MO 与 PG 两条链路均通过。点层隐藏后，线和面渲染的颜色像素也通过核验|

本轮提供的是上述选定工作流的端到端功能验证，**不表示这五个应用的所有功能、所有插件或生产规模负载均已兼容**。pygeoapi 的混合负载为 8 个 worker、40 次确认写入、40 次整集合并发读取及 8 次最终值核验；不能解释为长期极限吞吐量测试。QGIS 的坐标投影由客户端完成，不是 MO 数据库内 ST_Transform 的验证。

## 一个新增、已复现并提交的 MO 缺陷

[英文 issue #30046](https://github.com/matrixorigin/matrixone/issues/30046)：`GEOMETRY` 返回类型声明为 MySQL type 255，实际值却是 ASCII WKT，而不是四字节 SRID + WKB。GDAL/QGIS 的原生 MySQL 驱动因而丢失几何。相同 SRID 0 的点在 MySQL 返回 25 字节，在 MO 返回 17 字节 WKT；两者显式 ST_AsWKB 相同，排除了 EPSG:4326 的轴序干扰。

证据：`gdal-wire-probe.json`、`geometry-wire-minimal-repro.json`、`qgis-native-probes.json`、`issues/geometry-wire-format.md`。本轮 MO 日志未发现 `panic:`、`fatal error:` 或 `DATA RACE`。最初 QGIS 客户端因测试脚本析构顺序出现的崩溃已修正，保留初始记录，不能算作 MO panic。

其他不兼容项分别处理：

- GeoTools 用 `ST_asWKB(ST_SRID(ST_Envelope(ST_SRID(geom,0)),ST_SRID(geom)))` 编码 bounds；MO 的 SRID setter 要求常量。这是与固定列 SRID 类型有关的限制，当前可用独立应用方言适配。
- pygeoapi 原 MySQL provider 的 bbox SQL 未指定 SRID，MO 和 MySQL 均失败。MySQL 的 EPSG:4326 轴序还造成 GeoServer/pygeoapi 写入失败。这些不能直接计作新增 MO 缺陷。
- uMap 的 MO 原生迁移被 `CHECK ... ENFORCED` 的 ALTER 路径阻断；MySQL 参考也在后续迁移的 `gen_random_uuid` 处失败。已有 Postgres ArrayField/地理字段等依赖，不能宣称数据库完全可替换。
- MO 对 SRID 4326 的空间索引过滤下推有明确的正确性限制；本轮读查询通过不代表地理空间索引加速已满足大规模性能需求。

## 数据、计数和证据

共享合成数据：259 点（北京 16×16 网格、上海、纽约、日界线），16 条线，4 个多边形（含洞和日界线场景），8 个混合几何（含 multipart、collection），以及 SRID 0 对照点。中文、引号、JSON 数组与 NULL 一起测试。服务只绑定本机，测试只写 `gis_app_suite` / `gis_app_umap`。

`workflow-summary.json` 按 project/engine/phase/workflow 区分独立工作流与重复执行；`workflow-results.jsonl` 保留早期配置失败和后续修正，不把重复执行当作新增用例，也不把失败记录数当作独立 bug 数。原有 600,000 条主 case 数量不变，本套件单独计数。迁移日志、原生驱动探针和浏览器诊断另作证据。

关键证据：

- `source-manifest.json` / `geoserver-download-manifest.json` / `runtime-provenance.json`：源码提交、发行包 URL/SHA256、实际运行版本；pygeoapi SQL provider 和 uMap models 的已安装源码与固定发行源码逐字节相同。
- `geoserver-*-http.json`、`pygeoapi-http.json`、`umap-http.json`：实际请求与响应。GeoServer 原生失败后保留已提交的插入/更新证据，并只清理该工作流的合成行。
- `qgis-*-project.qgz` / `qgis-*-export.gpkg` / `qgis-*-map.png`：真实工程、空间导出与绘图。
- `maputnik-*-edited.png` / `maputnik-*-lines-polygons.png` / `maputnik-*-exported-style.json`：真实 UI 编辑、线面渲染及再导入；PNG 颜色像素核验保存在 `maputnik-render-pixel-verification.json`。
- `umap-export.umap` / `umap-mo-live-map-popup.png`：带远程 MO 数据源的地图备份与中文弹窗。

发行包从公开 TLS 地址下载并记录本地 SHA256，不声称已取得并匹配独立的官方发布校验值。浏览器使用真实 API 数据；外部底图关闭，RTL 脚本使用固定版本的本地副本。源码、下载包、运行时依赖和 DB 数据不上传；其固定版本及复现配置保留。上传的文本已剔除登录 CSRF token、会话 cookie 和调试 PIN；原始材料仍在本机。

## 复现

默认路径是本云环境 `/workspace/mo-gis-app-projects`；换机器时先调整 `common.py`、settings/config 中的测试路径与端口。所有密码是仅用于本机合成环境的默认值。

1. 按固定源码/发行包清单准备五个应用。GeoServer 安装官方同版本 MySQL plugin；Python 依赖见 `python-requirements-lock.txt`。QGIS/GDAL 使用系统 `/usr/bin/python3`；Java 21 的 compiler module 可用于构建 SPI。
2. 启动独立 MO、PostGIS、MySQL 参考实例后运行 `bootstrap.py`（会重建专用测试库/表）。已有测试库的用户数据应另存，不要改成业务库。
3. 使用 `pygeoapi-calibrated.yml` 和 `mo_geoapi.py`，生成对应 OpenAPI，启动 `run_pygeoapi.py`。配置 MO/PG 为物理 XY 的 CRS84、MySQL 为 EPSG:4326，避免误把配置轴序问题算成 MO 缺陷。
4. 运行 `adapters/build_geoserver_adapter.py`，重启测试 GeoServer 后运行 `geoserver_test.py` 的 native/adapted 两种模式；`pygeoapi_test.py` 使用真实服务测试 API 与混合负载。
5. uMap 使用 `umap-settings.py`、`umap_urls.py`，先 PostGIS migrate/collectstatic，准备合成用户 `gisowner`/`gisoutsider`，运行 `umap_test.py`；MO/MySQL 原生迁移失败记录另存。
6. `QT_QPA_PLATFORM=offscreen XDG_CONFIG_HOME=/workspace/mo-gis-app-projects/qgis-config XDG_CACHE_HOME=/workspace/mo-gis-app-projects/qgis-cache XDG_RUNTIME_DIR=/workspace/mo-gis-app-projects/qgis-runtime /usr/bin/python3 qgis_workflow.py`。QGIS cache 路径需存在。
7. Maputnik 在固定提交执行 `npm ci`、`npm run build`、`npm run lint`，本轮均通过。`serve_maputnik.py` 提供原发行构建；`browser_test.js` 用系统 Chromium/Playwright 执行真实 UI。Playwright 导入路径可按安装位置调整；本轮未运行上游 Cypress 套件。

服务配置/启动信息另见 `ENVIRONMENT.md`。这些步骤和代码是可检查的重放材料；未在第二台全新机器上验证完整重建。
