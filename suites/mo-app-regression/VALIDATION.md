# mo-test 接入实跑验证

本轮在隔离环境实际运行 MatrixOne 官方稳定版 v4.2.5，完整构建 SHA `1a44f3db3056e32975fde86ca0ab69a094996a3f`，运行时 git_version `1a44f3d`。结果记录使用 UTC 时间；每个业务驱动使用全新的随机库。

| 验证 | 实际结果 |
| --- | --- |
| Python 合同测试 | 14 项通过，覆盖错误签名、失败继续执行、缺失报告、观察标签、健康失败、panic opt-in、未迁移应用、commit 和低磁盘负载拒绝 |
| Gotify 原生业务 | 12 项通过：16 消息 / 4 workers，真实 API、SQL、权限和重启 |
| Blocky 原生 DNS | 10 项通过：64 查询 / 4 workers，精确持久化日志和真实重启 |
| Plik 原生文件服务 | 17 项通过：16 文件 / 4 workers，原生认证/CSRF、字节/MD5、权限、SQL、重启和删除 |
| Ergo 原生聊天历史 | 13 项通过：16 消息 / 2 writers，原生 fakelag 保留，IRC/SQL/权限/重启 |
| smoke SQL 对照 | 3 项通过：Unicode/JSON、事务回滚、生成列 UPPER 索引 |
| 全部 20 SQL fixture（观察） | 17 known_failure、3 passed，所有触发后健康检查通过；观察返回 0，但 suite passed 为 false |
| 严格缺陷门禁（默认不含 panic） | 13 known_failure、3 passed，正确返回 1 |
| 错误完整 commit | 在创建测试库前阻止，返回 2，jobs 为空 |
| 默认磁盘阈值 | 2 GiB 入场要求因本地约 330 MiB 余量被拒绝，返回 2，jobs 为空 |
| 凭据检查 | 对当前检出的 115 个公共文件检查 113 个历史私有值，无命中；runtime/artifacts 未提交 |
| Workflow | YAML 与接入字段校验通过；没有在 GitHub Actions 执行，没有配置或改写仓库密钥 |

证据目录：[evidence/integration/](evidence/integration/)。每个应用和 SQL 执行均保留 JSON / JUnit。主入口子任务级 JUnit 与子目录断言级 JUnit 是不同粒度，不能相加当作独立业务检查数量。

第一轮 Gotify / Ergo / 3 个 SQL 对照通过，Blocky 和 Plik 因各自旧的 2 GiB 保护被阻止，最终返回 1。该轮原始失败保存为 `integration-smoke`。统一入口与两驱动的入场阈值、直接使用同 SHA 本地二进制后，独立第二轮 `integration-smoke-round2` 全部通过；没有覆盖第一次失败。

本次有限基本验证显式使用 `--min-free-mib 128`，二进制逐一校验 SHA，直接执行本地文件，不复制或重新下载。默认 CI 仍要求 2048 MiB；低阈值原生验证要求已有二进制，Blocky/Plik 限定基本工作量，load profile 仍要求至少 2048 MiB。本次没有执行 load profile，也没有声称达到饱和容量。

17 个已知失败中包含 4 个既有恢复型 panic；这不代表本轮新发现 4 个独立 panic，也不代表服务进程退出。已有 main 的状态与稳定版不同，本轮不对最新 main 宣称缺陷仍存在，不提交新 issue。新增 issue 仍须按 MAIN-VERIFICATION.md 实际验证当时 main。

首批导入时，历史 58 个基本业务通过中的其余 54 个尚未做成独立驱动；61 个历史尝试中有 57 个驱动待迁移。1000 项总任务仍有 939 项未运行。此 PR 是已具备独立驱动的首批接入。


## 后续独立驱动迁移批次

本轮新增 6 个驱动，独立应用总数从 4 增至 10；原来 54 个待迁移的基本通过项目仍剩 48 个。候选 1000 项及 61/58/939 历史运行统计不因重复试跑而增加。

| 新驱动 | 独立新库实跑 | 关键范围 |
| --- | --- | --- |
| Documize v5.14.0 | 25 检查通过 | 官方二进制、35 原生迁移/27 表、原生 setup/登录/JWT、文档章节/FTS、SQL 逐值及重启 |
| Huginn d6f25e28 | 34 检查通过 | 校验 867 Git blob/适配、原生 73 迁移与 seed、Puma+AgentRunner 异步 Webhook→Formatter、权限/CSRF、SQL 与重启 |
| ntfy v2.29.0/f18d1137 | 40 检查通过 | 原生 CLI 账号/ACL、两用户共享 IP 并发身份、WebSocket/SSE、JSON/生命周期/附件、SQL 与重启 |
| Memos d5df8915 | 29 检查通过 | 原生管理员注册/账号、密码、私有笔记权限/并发 CRUD、SQL 精确归属与重启 |
| Baikal 0.12.1 | 44 检查通过 | 校验 1030 发行版文件、网页安装原生 14 表/账号、Digest CalDAV/CardDAV、ETag、BLOB/大小/UID/归属、重启删除 |
| FreshRSS 4a810f16 | 30 检查通过 | 校验 1294 blob/适配、完整网页安装、原生账号/API 密码控制器、Google Reader/RSS、两用户隔离、压缩正文/标记已读/令牌拒绝/重启 |

统一入口在新的官方稳定版实例再次执行 **10 个原生应用共 254 项检查 + 3 个 SQL 正向对照，全通过**，默认磁盘入场阈值 2048 MiB 保留。JSON/JUnit 见 evidence/migration-batch/all-ten-new-instance-smoke。这是基本业务回归，没有新增极限容量结论，也没有重计每次复跑。

workspace 剩余空间不足时，发现另外的 /tmp tmpfs 可用约 8.5 GiB，建立独立实例 6004（PID/目录见本地继续状态）。它使用官方 v4.2.5 同一完整 SHA 1a44f3db3056e32975fde86ca0ab69a094996a3f，独立 LOG/TN/CN UUID、部署 ID、所有服务端口与全新数据目录；GOMAXPROCS=2、Go soft limit=2 GiB。旧 6001 实例与旧数据没有停掉或删除。tmpfs 使用内存，不能当作持久磁盘扩容或独立机器容量。

ntfy 与 Memos SDK 均在另外的目录从固定完整源码实际重新构建，前者 622 原始 Git blob + 固定补丁，后者 1328 原始 blob；Go 1.27.1、独立缓存、构建 manifest 的实际二进制 SHA 绑定，随后分别新建库再运行 40 / 29 检查通过。第一轮 workspace 入场失败仍保留。冷构建使用明确的 CLI HTML 占位资源，完整 web UI 仍未验证；Huginn 全部依赖冷安装尚未在另一个全新 SDK 上重跑。

原始失败均保留：Huginn 首次运行配置路径错误，ntfy 最初把原生 WS（含 sequence_id）错误当成 HTTP JSON（ForJSON 省略它），Memos 最初用户名包含其原生规则禁止的下划线，FreshRSS 的 FrankenPHP getopt、未完成安装 finish 步骤、本地 RSS URL 默认拒绝、兼容 API 全角标题、原生初始订阅和压缩前缀假设，均为已修正的驱动/配置问题，不提交成 MatrixOne 缺陷。FreshRSS 只放行自建 RSS 服务的确切 IP:端口；SQL 验证编码原文与解压原字节，实测 COMPRESS framing 为长度前缀+raw DEFLATE，不认证跨厂商压缩 BLOB 互通。

GitHub Actions 尚未运行，相关 SDK/runner 配置见 RUNTIME-SDK.md。没有自动提交新 issue，新增数据库问题仍须先实际验证当时 main。

随后 Adminer v6.1.2 独立新库通过 20 项检查，原始两轮 CSRF 状态假设失败保留；原生非法 CSRF 返回403并明确提示，SQL确无改动。当前共11个驱动，原54项剩47项。本轮新增7个驱动共222项独立检查通过；加上原4个为274项。统一全10应用那一轮的254项记录保持不改，Adminer作为后续独立轮验证。

最终统一 smoke 再执行全部11个应用：**274个原生检查 + 3个SQL正向对照全部通过**。这轮 ntfy/Memos 使用本轮从源码构建并绑定 manifest 的二进制；默认为2048MiB磁盘入场要求，runtime 指向独立临时目录。证据见 evidence/migration-batch/all-eleven-cold-sdk-smoke。19项 Python合同/SDK身份测试、workflow YAML/11应用选择校验通过，GitHub Actions仍未运行。

## 继续迁移原54项：phpMyAdmin、Kanboard、YOURLS、Grafana

这四个新增驱动在每轮全新库中分别实跑22、34、28、27项检查，共111项。当前共15个独立驱动，原54项待迁移项目还剩43项；1000候选的61/58/939历史运行统计不变。

phpMyAdmin官方5.2.3的4314文件、Kanboard139原生迁移、YOURLS原生web安装/schema507、Grafana官方13.2.3的13361发行文件与853成功迁移分别核验；应用自己的安装、账号、认证与真实业务保留。SQL逐值核对、关联、原生权限拒绝、真实进程重启通过。Grafana官方包完整460956549字节流SHA匹配；alertmanager原生初始化仍报错，告警功能不认证。

随后通过统一入口再执行全部15个应用：**385项原生检查+3个SQL正向对照，全部通过、退出0**。证据见 evidence/migration-batch/all-fifteen-native-smoke；本轮ntfy/Memos仍使用冷构建SDK。Kanboard首轮把原生CSRF空请求返回200误判为应403，YOURLS首轮误把重复URL409预期为成功，均已按源代码和SQL零写入修正；原始失败JSON/JUnit保留。19项合同测试通过；GitHub Actions尚未运行，无新增issue。

Matomo 5.14.1 随后在独立新库通过30项检查，当前独立应用16个，原54项剩42项。本批截至目前总计415项原生检查实际通过；全部15应用的一轮385项保持原样，Matomo为随后新增轮次。原生install、34表、普通账号/权限/令牌、三独立访客、完整UTF8动作/URL/身份关联、Live报告、真实重启和原cookie/令牌读回均已验证。前六轮发行包根级说明文件、插件建表时机、API scalar包装/错误状态、默认访客指纹合并等驱动预期问题保留，不提交为MO缺陷。

Matomo 第一次统一入口复跑未创建管理员，原生 setupSuperUser 返回自身表单而非完成后的下一步骤，退出1。该次原始响应未保存，根因未确定，不能归为已修好的驱动假设或已确认MO缺陷。新增准确的步骤完成断言并保留后续每步私有原始HTML；同一失败密码在另一全新库复现时完整31项通过，排除了该密码固定不被接受的推测。此安装稳定性现象保留，不静默重试、不自动提issue，须进一步取得失败响应并在当时main实际核查后才能归因。Matomo当前驱动多了1项安装阶段断言，总计31项，所有16应用的各自通过检查共416项。30项的先前记录保持不改。

Matomo 随后第二次统一入口新库复跑，31项原生检查+3个SQL对照全部通过、退出0，证据见 evidence/migration-batch/matomo-entry-smoke-round2。第一次入口失败保持原样。当前416项来自15应用统一轮385项，加当前Matomo31项；不是声称单轮统一执行了16应用，也不叠加重复跑的检查。PHP配置引号/反斜线/美元符号/Unicode通过真实PHP执行逐字节hash核验；19合同测试及workflow YAML/16应用选择通过。GitHub Actions尚未执行。


## 继续迁移原54项：Gogs 与 Apache Answer

本轮新增 Gogs33项、Apache Answer27项，独立驱动共18个、原54项剩40项。当前18个驱动分别通过的原生检查合计476项；上一轮全15应用385项及Matomo31项的既有证据不改写。统一入口全新库执行这两个应用的60项检查加3个SQL正向对照全部通过，见 evidence/migration-batch/gogs-answer-entry-smoke。候选1000项、61个真实尝试、58个基本通过和939项未运行仍保持原统计。

Gogs 在私有原生仓库真实执行 HTTP Git clone、提交、push 和逐字节读取，验证4个顺序 issue、评论、原生密码/令牌及重启后权限。首次 readiness 路径不存在、默认页面需要 Vite、初次 auto_init 缺少原生 README 类型、SQL列名/HTTP返回值假设等六轮失败全部保留；这些失败不能直接判为 MatrixOne 缺陷。使用历史固定SHA二进制通过，不宣称冷 SDK 或前端验证完成。冷构建被4GiB空间入场检查阻止且 build_started=false，见 gogs-cold-build-blocked.json。原生并发 issue 编号竞争尚未修复、未认证高并发 issue 写入。

Answer 新库原生 AUTO_INSTALL、用户角色、问答/标签/Markdown逐值、拒绝路径及实际进程重启通过27项；另一个新目录默认从官方压缩包下载、验证固定摘要后同样通过27项。原始两轮失败分别来自测试误判旧 is_admin 字段及原生 answer/info 返回层级，保留于 answer-portable-round1/2；没有用SQL修补账号、迁移记录或业务数据。本轮未发现新的已证实MO缺陷、未提交新issue；后续新问题仍须在当时 main 的实际运行时复核。


## OpenCart：原54项还剩39项

第三个新增驱动OpenCart4.1.0.4在全新库通过35项：官方包完整SHA、原生网页安装159表/管理员、密码登录/错误密码、原生login_token与user_token、Unicode商品描述/店铺关联、四条精确价格规则、未来/过期较高优先级规则排除、10%折扣22.50/减5特价20.00、购物车数量2/总额40.00、匿名及非法token零写入、真实进程重启后cookie/商品/购物车读回和原生更新。原生文件session/cache保持，不认证订单/支付/运费/全量插件及已有数据升级。

原始失败轮次全部保留：PHP8.5弃用PDO常量使原生JSON出现提示，增加同义新常量兼容；私有凭据文件的O_EXCL重复创建；价格日期局部变量覆盖启动函数，均在harness/SDK层修正，不归为MO故障。第四轮通过。当前19个驱动分别通过的原生检查合计511项；本轮3个新增驱动合计95项，原54项已迁移15个、还剩39个。1000候选及61/58/939历史统计不增加。

统一入口在另外三个全新库重跑 Gogs33、Answer27、OpenCart35，加3项SQL正向对照全部通过，退出0。OpenCart此次使用默认官方下载路径，完整zip摘要仍匹配；见 evidence/migration-batch/gogs-answer-opencart-entry-smoke。20项分类/入口/SDK合同测试通过；新增驱动load入口和线上GitHub Actions未执行。


## Wakapi：原54项还剩38项

Wakapi 第七轮全新库通过40项：14张原生表及外键、三账号/Argon2id/角色/原生API key、两普通用户并发16条心跳、16条全量落库逐值/时间/用户/FK/uint64 ID核对、重复提交去重、匿名/错误key/跨用户读写拒绝、真实重启后SQL/API/cookie一致。重复提交不计为新增持久化心跳。当前共20个独立驱动，原54项已迁移16个、还剩38个；各驱动分别通过原生检查共551项。本轮新增4个驱动共135项；候选1000/尝试61/基本通过58/未运行939不增加。

原始失败保留：前两轮误选归档的未适配官方二进制，第一轮IP站点被WebAuthn拒绝、第二轮未适配metadata出现重复FK；最早的report provenance标签有误，解释见wakapi-sdk-selection-audit.json，不能当作适配SDK或新MO缺陷。正确SDK第三/四轮遇到原生邮箱MX规则（使用原生可选空邮箱保持规则），第五轮Python HTTP header编码失败（机器名用ASCII，业务JSON仍为Unicode）。第六轮重启90秒检查超时，第七轮将重启有界等待设为180秒，实际首启63.164秒、重启125.136秒后全部40检查通过；这只证明本轮基本业务与重启通过，不能解释为慢启动已修复或生产启动性能合格。慢启动根因尚未隔离，与MySQL/main对照未完成；未提交新数据库issue。完整冷SDK因不足4GiB保护未执行，使用固定历史适配二进制。

Wakapi经统一入口另建新库复跑40项原生检查加3项SQL正向对照通过，退出0，见 evidence/migration-batch/wakapi-entry-smoke；其启动耗时逐轮记录，不覆盖第六轮90秒超时。21项Python合同测试及20应用workflow选择校验通过。三应用联合95项轮与本轮Wakapi40项轮分开，未宣称一次全20应用联合运行；线上CI和新增load入口尚未执行。


## 热门项目迁移：Superset、Strapi，原54项还剩36项

本轮优先迁移历史星数75100的Apache Superset及73290的Strapi。Superset第一次32项通过，随后使用可移植稳定包文件清单和升级日志门禁在全新库通过33项；core源码私有副本实际导入断言加入后，统一入口另一个新库33项加3项SQL对照通过。SDK162包/15043稳定文件、27 core blob，原生344 Alembic升级/版本head、Admin/Gamma账号/角色、SQL Lab原生创建/写入1000行Unicode数据/500500聚合、数据集/图表/仪表板关联、非所有者拒绝/非法CSRF零写入、指定ENUM真实拒绝、实际重启全部通过。第一轮的SDK清单包含安装器路径相关元数据，第二轮开始排除这些安装器细节但保持全部运行包文件绑定，不将该变化计为新的业务通过项。

Strapi第五轮32项通过：原生44表、Super Admin及Author真实注册/密码/角色、原生内容API令牌、文章草稿与发布两版本、两份关联/创建者/Unicode逐值、匿名/错误token/Author管理用户和token拒绝、更新/再发布和真实重启后SQL/API一致。原始第一轮未创建uploads目录及默认XDG写路径失败保留；后续两轮关系category.name四字节字符失真保留，SQL原文正确、文章及关系ID均正确。第四轮记录元数据证实派生name列db/table为空；仅这一个VAR_STRING形状补充UTF8解码，第五轮精确断言及重启通过。所有失败保持failed，不归为已修复数据库故障；相关main对照未完成，没有提交新issue。

当前22个独立驱动分别通过的原生检查合计616项，本轮新增65项；原54项已迁移18个、还剩36个。1000候选/61历史尝试/58基本通过/939未运行不增加。新增两个load入口、完整冷依赖安装及线上CI尚未执行。Superset源仓库与Strapi monorepo均未修改或推送，本次适配和驱动只在独立mo-test套件中。旧库、旧runtime和原始归档/缓存保持。

Strapi统一入口另一个全新库32项加3项SQL正向对照通过，退出0。二进制字段入场检查额外使用LOWER(data_type)对实际44表schema读回验证为0，保留相同四字节字符断言；所有生成的auth密钥保存在私有凭据文件。两个新增应用的统一入口轮分别记录，未宣称一次全22应用联合运行。Superset首轮完整旧SDK清单按其实际report hash精确恢复保留，供审查早期SDK身份。


## WordPress 与 Wagtail：原54项还剩34项

本轮新增WordPress33项、Wagtail46项，共79项。24个驱动分别通过的当前原生检查共695项；原54个待迁移应用已完成20个、剩34个。1000候选/61历史尝试/58基本通过/939未运行不增加，没有把重复回归当成新项目。

WordPress固定历史7.2-alpha-64292源码5028 Git blob，原生网页安装12表、管理员原生密码/cookie/REST nonce、原生应用密码、订阅者、草稿/发布/分类/评论/修订、四字节Unicode逐值SQL、错误应用密码/匿名/订阅者/非法nonce零写入、真实PHP进程重启、应用密码吊销后拒绝通过32项。第一轮错误假设首个草稿必有修订记录；第二轮通过两次原生发布更新核对前后已发布修订，保留第一轮失败。另一个新库从统一入口复跑32项+3项SQL对照通过，退出0，见 wordpress-entry-smoke。不是稳定版WordPress或完整插件/升级/负载认证。

Wagtail官方8.0 wheel与准备SDK核对4250应用文件，只有0086精确适配，其原始内容与固定Git blob一致。41依赖包/10230稳定文件、解释器SHA和独立HomePage fixture受核验。原生185计划节点、222记录（含squashed替代旧迁移）及53表、原生createsuperuser、Django原生create_user/Permission ORM观察者、真实登录和页面表单、草稿/发布版本与修订JSON、页面树/子类关系、Unicode、有效CSRF下权限拒绝、非法CSRF零修订、真实Gunicorn重启及取消发布通过46项。观察者仅获access_admin，无页面权限；原生拒绝会跳回后台并带精确错误消息，不把普通HTTP200算拒绝通过。

前四轮失败逐一保留，见 WAGTAIL-FAILURES.md：计划/recorder断言、漏启用wagtail.users、原生多FULLTEXT写入panic、原生权限跳转断言。第三轮panic已匹配PANIC-04/#29899，在保留的新库经真实表单独立捕获模板/参数和完整SHOW CREATE TABLE；公开的完整复现SQL及触发后健康核对保存，未观察到服务器进程退出。后续业务通过使用历史原生fallback后端，不删除FULLTEXT索引或改写原有失败。未完成本次main候选21f19ae…的运行验证；构建在入场前因资源不足阻止，未重复提issue，未宣称main已修复。

本轮仅运行两个新驱动及各自入口，不声称一次完整重跑24应用。新增load入口、Wagtail完整冷依赖安装、全部UI和线上Actions尚未完成；基本验证使用显式1024MiB缓存SDK入场阈值，load最低2GiB规则保留。


Wagtail经统一入口在另一个全新库复跑，46项原生检查加3项SQL正向对照通过，退出0，见 evidence/migration-batch/wagtail-entry-smoke。WordPress和Wagtail各自的统一轮分开保存，未宣称一次完整24应用联合运行。新增SDK身份拒绝与venv路径保护合同测试两项，当前共25项Python合同测试通过；24应用workflow选项和两个新SDK变量已核对。


提交前额外复核WordPress旧32项通过轮的原生私有日志，发现两条后台分类查询仍报SELECT DISTINCT排序列未选中；这不影响当时32个业务断言结果，但不能把旧轮称为无数据库错误。完整旧drop-in与结构化日志审计保留于 wordpress-initial-db.php / wordpress-initial-log-audit.json，查询见 wordpress-distinct-term-query.sql。原补丁只覆盖term_id单列查询，新补丁同时覆盖term_id、object_id双列形式，补选由term_id主键唯一决定的name，保持DISTINCT基数。第三轮新库通过新增的“原生WordPress日志无数据库错误”门禁，全部33项通过；当前各驱动检查总数更新为695，本轮两个应用合计79项。未发布新数据库issue，仍未完成本次main运行验证。


修补后的WordPress统一入口再次在全新库执行，33项原生检查（含日志零数据库错误）加3项SQL正向对照全部通过、退出0，见 evidence/migration-batch/wordpress-entry-smoke-round2。旧32项入口及其两条后台SQL错误审计保留，不覆盖、不叠加重复计数。同步到mo-test/main的4fcb1c5后保留了已有AI框架回归内容，本批仅修改应用套件及其入口和说明。
