# qqnt-chat-decrypt

QQ NT 聊天记录解密与导出工具集 —— 从手机备份 `.bak` 文件或桌面端本地数据库，导出完整聊天记录为 txt / HTML。

> ⚠️ 仅供导出**自己的**聊天记录使用。解密依赖本机已登录的 QQ，不绕过任何认证。密钥等于账号所有聊天库的钥匙，请勿外传。

## 背景：为什么这个仓库存在

QQ NT（新版 QQ）把聊天记录存在 SQLCipher 加密的 SQLite 里，2024 年后的新格式：

- 数据库文件头（前 1024 字节）里的 128 位 hex 串是 `key_meta`（数据库标识），**不是密钥**
- 真正的 `db_key`（16 字节随机 ASCII）是客户端登录时用 `key_meta` 向腾讯服务器（OIDB `0xcde_2`）换取的，**无法离线推导**（旧版 `md5(md5(uid)+rand)` 公式已失效）
- 密钥**按设备独立**：同一账号 Windows / macOS / 手机各有一把不同的钥匙；手机备份 `.bak` 里的库还有备份时单独生成的密钥

所以本仓库的思路是：**密钥就在已登录的 QQ 进程内存里，把它取出来**。

社区已有的方案（[QQBackup](https://github.com/QQBackup) 等）主要覆盖 Windows（进程内存扫描）和 root 安卓（frida hook）；macOS 侧教程依赖断点在 `nt_sqlite3_key_v2` 函数上，但该函数在 QQ 7.x 上没有符号、地址定位不稳，且引导期附加调试器会让进程自僵死。本仓库提供一个更稳的 macOS 路线：**lldb 堆转储 + 候选剪枝 + sqlcipher 本体验证**，全程不需要逆向函数地址。

## 完整步骤

### 场景 A：你有一个 `.bak` 备份文件（"xxx的N个聊天记录.bak"）

`.bak` 本身无法离线解密，最短路径是走官方恢复：

1. 在 QQ 桌面端/手机端执行「**导入聊天记录**」，选择该 `.bak`
2. QQ 会用你的登录会话向服务器换取备份密钥并解密，消息合并进本地 `nt_msg.db`，文件和图片解密落地 `nt_data/`
3. 然后走场景 B，把本地库导出

`.bak` 的结构分析（ZIP / MSG0 头 / key_meta 机制）见 [docs/bak-format.md](docs/bak-format.md)。

### 场景 B：导出 Mac 本机的聊天记录（核心流程）

#### 0. 准备

```bash
brew install sqlcipher
```

要求：Mac 上装着 QQ 且能登录目标账号。

#### 1. 重签名 QQ（解除 lldb 附加限制，约 1 分钟）

```bash
sudo codesign --remove-signature /Applications/QQ.app
sudo codesign --force --deep --sign - /Applications/QQ.app
```

重装 QQ 即可还原官方签名；数据不受影响。之后偶尔提示「QQ 已被修改」忽略即可。

#### 2. 启动 QQ 并登录

**用二进制直接启动**，不要 `open -a`：

```bash
/Applications/QQ.app/Contents/MacOS/QQ > /tmp/qq.log 2>&1 &
```

未沙盒化的 QQ 读取的是 `~/Library/Application Support/QQ`（而不是容器目录）。若要让它用容器里的原登录数据，建立软链接：

```bash
mv ~/Library/Application\ Support/QQ ~/Library/Application\ Support/QQ.fresh 2>/dev/null
ln -s ~/Library/Containers/com.tencent.qq/Data/Library/Application\ Support/QQ ~/Library/Application\ Support/QQ
```

等 QQ 完全启动、**登录进入主界面**（日志里出现 `OnLocalDataInitComplete`）。

> 踩坑记录：引导期就附加 lldb 会让 QQ 自僵死（主进程在但永远不出窗口）；`open -a` 启动的实例在反复强杀后也容易僵死。务必等登录完成后再附加。

#### 3. lldb 附加 + 堆转储

```bash
QPID=$(pgrep -x QQ | head -1)
lldb -b -p $QPID \
  -o "command script import $(pwd)/scripts/dump_heap.py" \
  -o "dump-all" -o "detach" -o "quit"
# 产出 /tmp/qq_heap.bin（约 1.6GB）与 /tmp/qq_heap.idx
```

#### 4. 提取密钥（堆扫描 + sqlcipher 验证）

```bash
# 先给 nt_msg.db 去头
QQDB=~/Library/Containers/com.tencent.qq/Data/Library/Application\ Support/QQ/nt_qq_*/nt_db/nt_msg.db
tail -c +1025 $QQDB > /tmp/nt_msg.clear.db

python3 scripts/find_key.py /tmp/qq_heap.bin /tmp/nt_msg.clear.db
# 命中后密钥写入 ./found_key.txt
```

原理：`db_key` 是 16 字节可打印 ASCII，且在进程内必然有多份 `std::string` 拷贝。脚本提取所有出现 ≥2 次的 16 字节可打印串（约 1200 个候选），逐个按 QQ 的 SQLCipher 参数喂给 `sqlcipher`，能打开即命中——**让 sqlcipher 自己当验证器，不要手工复刻密钥派生公式**。

#### 5. 解密导出

```bash
KEY=$(cat found_key.txt)
./scripts/decrypt.sh "$KEY" $QQDB nt_msg_plain.db
```

> SQLCipher PRAGMA 顺序是硬约束：`cipher_page_size` 必须在 `key` **之前**；`kdf_iter` / `cipher_hmac_algorithm` / `cipher_kdf_algorithm` 必须在 `key` **之后**。顺序错了会报 `file is not a database`。

QQ NT 参数：`cipher_page_size=4096`、`kdf_iter=4000`、`cipher_hmac_algorithm=HMAC_SHA1`、`cipher_kdf_algorithm=PBKDF2_HMAC_SHA512`、AES-256-CBC。

#### 6. 导出聊天记录

```bash
# 定位对方 uid（用会话中出现过的关键词反查）
sqlite3 nt_msg_plain.db "SELECT [40020],[40021] FROM c2c_msg_table WHERE [40800] LIKE '%关键词%' LIMIT 5;"

# 我的 uid 可以这样验证：md5(md5('<uid>')+'nt_kernel') 应等于 nt_qq_ 后缀

python3 scripts/export_chat.py nt_msg_plain.db <我的uid> <对方uid> <对方昵称> ./聊天记录
# 产出 聊天记录.txt 和 聊天记录.html
```

消息表结构与 40800 protobuf 字段说明见 [docs/msgdb-schema.md](docs/msgdb-schema.md)。

#### 7. 清理

```bash
rm /tmp/qq_heap.bin /tmp/qq_heap.idx /tmp/nt_msg.clear.db
rm ~/Library/Application\ Support/QQ          # 删软链接
rm -rf ~/Library/Application\ Support/QQ.fresh
```

## Windows 用户

Windows 上有更简单的现成方案（进程内存扫描，无需重签名）：

```powershell
# https://github.com/QQBackup/qq-win-db-key
powershell -ExecutionPolicy Bypass -File .\windows_ntqq_get_key.ps1
```

注意 Windows 提取的密钥**开不了** macOS 的库（密钥按设备独立），但可以解 Windows 本机的数据库（流程同上，去掉 1024 字节头后参数一致）。

## 常见问题

| 症状 | 原因 |
|---|---|
| `file is not a database` | PRAGMA 顺序错误（见步骤 5）；或密钥不对；或没剥前 1024 字节头 |
| 附加 lldb 后 QQ 卡死不出窗口 | 引导期附加会触发自僵死——等登录完成后再附加 |
| `open -a` 启动的 QQ 没有渲染进程 | 反复强杀后的状态残留——用二进制直接启动 |
| 断点法抓不到密钥 | QQ 7.x 无符号且函数布局变化，用本仓库的内存转储法 |
| .bak 直接解密失败 | 正常，备份库有专用密钥，走官方导入 |

## 致谢

- [QQBackup/qq-win-db-key](https://github.com/QQBackup/qq-win-db-key) 与 [QQDecrypt 文档库](https://qqbackup.github.io/QQDecrypt/) —— 密钥机制逆向与各平台教程
- [QQBackup/nt_msg_db_util](https://github.com/QQBackup/nt_msg_db_util) —— 消息表字段文档与导出工具
- [sqlcipher](https://github.com/sqlcipher/sqlcipher)

## License

MIT
