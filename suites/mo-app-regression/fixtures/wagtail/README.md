# Wagtail 8.0 SDK 身份与适配

固定源码为 `24e624cc63b5d17a1ff1c1cd0d0e0817524cbd8d`。从 PyPI 下载官方 8.0 wheel，完整 SHA 与 PyPI 元数据核对；4,250 个应用文件与准备好的 SDK 比较，除 `0086` 的精确迁移适配外全部一致。原始 `0086` 同时与该提交的 Git blob 比较。证据见 official-wheel-audit.json，原始/适配文件及补丁均可审查。

sdk-manifest.json 绑定准备好的 Python 3.12 解释器和 41 包、10,230 个稳定包文件。排除安装器记录、路径相关 direct_url 与 bytecode，实际运行代码和包元数据仍固定。requirements-sdk.txt 固定版本，尚不是带完整 wheel hash 的冷安装锁；没有完成全新机器上的完整依赖安装。准备 SDK 后可使用以下形式执行：

```json
{"python_binary":"/owned/wagtail-venv/bin/python"}
```

把文件路径配置为 MO_WAGTAIL_RUNTIME_CONFIG；解释器、每个依赖文件和适配迁移必须与清单匹配。不自动安装或修改提供的 SDK；运行副本只复制本目录 project 的固定 fixture，不复制旧配置、账号、媒体或数据。解释器路径保留 venv 语义，不解析成全局 Python；使用独立 bytecode 查找路径和禁止写 bytecode，避免原 SDK 的旧 bytecode 绕过源码核对。

matrixone_backend 保留已有适配：拆开 ADD COLUMN 与 FK；JSON 默认值显式回填；从 SHOW CREATE TABLE 读取约束；仅在已有索引名称、列和唯一性一致时跳过重复创建；完整 GROUP BY；禁用不支持的 SAVEPOINT；限定合法 tree path 前缀改用 LEFT；删除无关列时暂时拆下并恢复自外键。特定旧权限 CHECK 在确认无 NULL 后改为更强的 NOT NULL；通用 CHECK、降级与已有数据升级未认证。0086 用同一原生 ORM/权限查找逐行更新替代相关 UPDATE；这不代表原始 panic 已修复。

project 是小型原生 HomePage CMS fixture；原生 migrate 创建全部表和初始页，原生 createsuperuser 创建管理员。普通观察者由明确的 fixture 命令调用 Django create_user/Permission ORM 创建，只获 access_admin，无页面权限；不通过 SQL 插入用户、权限或迁移记录。页面及修订全部通过真实管理页表单创建和变更。Python 数据库写操作只新建随机数据库，其余为独立读回。

默认磁盘入场阈值 2 GiB；缓存 SDK 的基本运行允许显式降低至至少 128 MiB并记录。未实现 load 入口，不认证完整静态界面、StreamField、搜索、上传、工作流或长期性能。
