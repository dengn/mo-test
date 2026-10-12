# 导入来源与范围

源仓库：matrixorigin/matrixone-app-regression，固定 commit `e3f59736522ec3128cc47b541d292fafc6dcfbd1`。

`upstream-import.json` 保存导入时逐文件 SHA-256；`artifact-manifest.json` 保存 mo-test 接入后的文件 SHA-256，两者含义不同。原生应用二进制不提交，应用版本、下载地址及 SHA 均在驱动里。Ergo 上游默认配置附带其 LICENSE。

接入新增统一 run.py、profile、可复用 GitHub Actions、套件合同测试、目录验证与迁移清单；Gotify 增加直接传入同 SHA 官方二进制的选项；Blocky/Plik 对提供的同 SHA 二进制直接执行，避免重复复制，并与统一入口共享磁盘入场阈值。默认仍为 2 GiB，低阈值仅支持已有二进制的小规模验证，load 至少要求 2 GiB。main 要求和适配说明中的历史证据链接指向源仓库固定 commit，不复制庞大的历史证据与私有现场。

此处保留 1000 候选、61 次原生运行尝试、58 个基本业务通过、4 个独立原生驱动和 20 个 SQL fixture 的不同统计口径。不会据候选或历史清单声称其他应用已自动化。
