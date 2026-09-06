#!/usr/bin/env python3
"""从 QQ 进程堆转储中提取 16 字节密钥候选，并用 sqlcipher 验证。

用法: python3 find_key.py <heap.bin> <去头后的nt_msg.db> [候选最低出现次数,默认2]

原理:
- QQ NT 的 db_key 是 16 字节可打印 ASCII, 在进程内存中有多份 std::string 拷贝
- 提取所有前后带非可打印边界、恰好 16 字节的可打印串
- 只保留出现 >= N 次的(剪枝), 逐个按 QQ 的 SQLCipher 参数喂 sqlcipher
- sqlcipher 本体就是验证 oracle: SELECT count(*) FROM sqlite_master 不报错即命中
"""
import collections
import re
import subprocess
import sys

def sql_verify(db, key):
    safe = key.replace("'", "''")
    sql = (
        "PRAGMA cipher_page_size = 4096;\n"
        f"PRAGMA key = '{safe}';\n"
        "PRAGMA kdf_iter = 4000;\n"
        "PRAGMA cipher_hmac_algorithm = HMAC_SHA1;\n"
        "PRAGMA cipher_kdf_algorithm = PBKDF2_HMAC_SHA512;\n"
        "SELECT count(*) FROM sqlite_master;\n"
    )
    try:
        r = subprocess.run(["sqlcipher", db], input=sql, capture_output=True,
                           text=True, timeout=30)
    except Exception:
        return False
    return "rror" not in (r.stdout + r.stderr)

def main():
    heap_path, db = sys.argv[1], sys.argv[2]
    min_count = int(sys.argv[3]) if len(sys.argv) > 3 else 2

    print(f"[*] 读取 {heap_path} …")
    data = open(heap_path, "rb").read()

    # 恰好16字节可打印、前后是非可打印边界
    pat = re.compile(rb'(?<![\x20-\x7e])[\x20-\x7e]{16}(?![\x20-\x7e])')
    counts = collections.Counter(pat.findall(data))
    multi = {k: v for k, v in counts.items() if v >= min_count}
    print(f"[*] 候选 {len(counts)} 个, 出现>={min_count}次的 {len(multi)} 个")

    def plausible(b):
        if b.count(b" ") > 3 or b.isdigit() or b.isalpha():
            return False
        return True
    cands = [k for k in multi if plausible(k)]
    print(f"[*] 启发式过滤后 {len(cands)} 个, 开始逐个验证…")

    for i, k in enumerate(cands):
        key = k.decode()
        if i % 200 == 0:
            print(f"    … {i}/{len(cands)}")
        if sql_verify(db, key):
            print(f"\n[+] 找到密钥: {key}")
            print(f"[+] 出现次数: {multi[k]}")
            with open("found_key.txt", "w") as f:
                f.write(key)
            return 0
    print("[-] 未命中。可降低出现次数门槛重试, 或确认 heap 转储时 QQ 已登录")
    return 1

if __name__ == "__main__":
    sys.exit(main())
