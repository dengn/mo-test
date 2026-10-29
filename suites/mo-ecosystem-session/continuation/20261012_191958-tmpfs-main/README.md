# 临时盘主计划续跑：已执行检查点

此快照以 summary.json 时间与实际记录为准。用户已明确允许在独立/tmp的新MO/MySQL/MinIO续跑主计划，旧数据全部保留。pandas新增部分、SQLAlchemy及PyMySQL等真实原生API写入与显式效果适配运行中；不把先前的SDK归档来源预检或Iceberg只读补测抵扣主计划。

完整类型窗口数据保持原字节。此快照先冻结完成的归档窗口，再读取case记录，独立解压CRC、逐表行数/行哈希，恢复Decimal/float-hex/binary/date/datetime/time/set/null等类型，对每个case重算已记录的expected_sha256和行数。案例原始fixture期望不重新生成。当前窗口中已执行但未完成归档的记录只计为待下次窗口核对；对应数量在summary中单列。

case是类型×场景×种子×端点的参数化行集断言，含MySQL对照；不是独立DAG/故障次数。32–256物理行/案例，含宽Unicode、负TIME、Decimal65、UInt64、BIT64、JSONnull/SQLNULL、ENUM/SET、UUID等。显式SQL合并/删除/回滚/DDL/幂等重放适配及原来的类型约定保留；不推导原生跨系统EOS。FLOAT32六位有效数字、CHAR尾空格裁剪、桥接中的明确表示转换仍适用。

MO仍固定652c643666428f1c434e03369834f2a9bead7c27及原binary；MySQL8.4.11。逻辑角色6001/13306的新物理端口16001/23306，runtime_id在新增case中记录。新服务所有存储/日志/配置均在独立/tmp，2个case工作线程、每窗口20场景；临时使用上限4GiB、保留至少2GiB、估计内存余量至少3GiB保护。内存临时盘与较小cache/redo配置只支持本轮有限功能场景，不能作为磁盘吞吐或长稳认证。

保留初次MySQL启动失败：发行包secure-file-priv默认路径不存在，已配置到新实例目录并复用本轮自己的初始化状态，没有重新初始化或删除数据；修正后首个20场景窗口全通过，再进入主批次。mysql-connector运行器的配置函数名限定已修正；源码保留运行过程差异，当前结果不把运行器错误归为MO bug。

evidence.zip包括本次已完成窗口的完整类型SQL数据/DDL、逐case记录和独立回读结果、配置/代码、初次启动日志；manifest.json校验全部成员和ZIP的SHA256、大小/CRC。口令均在发布文本中脱敏，数据/执行记录若匹配口令扫描则拒绝发布，完整类型数据保持原字节。本包不含安装程序、私钥、认证缓存或旧服务数据目录。

原生PyIceberg桥接代码在本快照时仅准备，尚未执行，不算入主计划完成数。其预定范围是原生typed append/scan与显式SQLsink，schema/效果适配；将对native与SQLsink的唯一性约束边界分别记录，不能当作官方MO connector。
