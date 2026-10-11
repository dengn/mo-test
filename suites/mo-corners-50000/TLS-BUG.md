# TLS SSLRequest 与 ClientHello 合并发送导致握手超时

同一 CA 的有效证书、相同协议与相同 SSLRequest 内容下，将 MySQL SSLRequest 和 TLS ClientHello 合并为一个 sendall：40/40 次握手失败（2 秒客户端超时）。两个 sendall 相隔 50 毫秒：40/40 成功。Python ssl.MemoryBIO 直接生成和校验 TLS，不依赖 PyMySQL 认证逻辑。

此外普通 PyMySQL 有效证书连接在串行 30 次中失败 6 次，在并发 100 次中失败 57 次；20 次额外时序对照为立即握手失败 4 次、延迟 50 毫秒失败 0 次。未将超时归为正确证书拒绝。

最小复现：tls-coalescing-repro.py；输出：tls-coalescing-repro.json。固定 MatrixOne 提交 2726fb419b3afa1db2686ae1b2aaca563d1ae214，Go 1.27.1，Linux，前端 TLS 开启。

疑似根因：pkg/frontend/mysql_buffer.go 的 Read 从 TCP 预读额外字节，RawConn 返回原始连接；pkg/frontend/server.go 将 RawConn 直接交给 tls.Server，可能忽略 SSLRequest 后已缓存在 Conn 内的 ClientHello。尚未修改代码或验证修复，根因描述是依据代码和时序实验的判断。

影响：正常 TLS 客户端连接可能失败；本次没有证据显示越权、TLS 降级成功或 panic。全部正反例原始记录保留。
