# QQ NT 聊天记录备份 .bak 格式

## 文件结构

`<QQ号>的<N>个聊天记录.bak` 本质是 ZIP（store 不压缩）：

```
files/9/<32位hex文件ID>     # 聊天中的文件附件（加密blob）
db/<32位hex库名>            # 4个 SQLCipher 加密数据库（消息本体）
```

## db 文件头（前 1024 字节，protobuf）

```
偏移 0:   "SQLite header 3\0"     # 伪装的 SQLite 头（正版是 "SQLite format 3"）
偏移 16:  04 00 XX 00 ...
偏移 32:  "MSG0"                  # 魔数（在线库/旧备份是 "QQ_NT DB"）
偏移 36:  uint32 LE = 后续 protobuf 长度
偏移 40:  protobuf:
            field 2 (len-delim, 128字节) = key_meta（128个hex字符=64字节）
            field 3 (len-delim) = 版本号（如 "1"）
偏移 46~53: key_meta 的第4~11个字符（旧格式此处是8字符rand）
其余:    0 填充
```

1024 字节之后是标准 SQLCipher 4 加密页（page 4096 / kdf 4000 / HMAC_SHA1 / PBKDF2_HMAC_SHA512）。

## 密钥机制（为什么离线解不了）

- `key_meta` 是数据库标识/兑换凭证，不是密钥
- 真正的 `db_key`（16字节随机ASCII）：登录会话中客户端发 OIDB `OidbSvcTrpcTcp.0xcde_2`（RequestDecryptKey），带 key_meta 向服务器换取；建库方向是 0xcde_1
- **key 按设备独立**：同账号 Windows/Mac/手机各不同；.bak 的库用备份时手机端 libmsgbackup 单独生成的密钥，账号密钥也开不了
- 旧格式（2024 前，头里 "QQ_NT DB" + 8字符 rand）：`key = md5(md5(nt_uid) + rand)`，nt_uid 是账号级 u_ 开头串（`md5(md5(uid)+"nt_kernel")` = 数据目录 nt_qq_ 后缀，可用来反查 uid 归属）

## 内容获取路径（按性价比排序）

1. **官方导入（推荐）**：QQ 桌面端/手机端「导入聊天记录」选 .bak → QQ 用账号会话向服务器换密钥解密 → 消息合并进本地 nt_msg.db，文件/图片解密落地 nt_data（File/Ori、Pic/<年-月>）。之后走 nt_msg.db 解密导出流程即可。
2. **直接解密 .bak**：需要 root 安卓机 frida hook（qq-win-db-key 的 android_get_backup_key 脚本，hook libmsgbackup），成本高。
3. 纯离线推导：不存在（服务器下发）。

## 导入后的落点（macOS）

```
~/Library/Containers/com.tencent.qq/Data/Library/Application Support/QQ/
  nt_qq_<hash>/nt_db/nt_msg.db                    # 消息（含导入的历史）
  nt_qq_<hash>/nt_data/File/Ori/<md5>_<uuid>/     # 还原的文件
  nt_qq_<hash>/nt_data/Pic/<YYYY-MM>/             # 还原的图片
```

导入成功的标志：QQ 顶部提示「成功导入N个聊天记录」。
