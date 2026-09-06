#!/usr/bin/env bash
# 解密 QQ NT 的 nt_msg.db 为明文 SQLite
# 用法: ./decrypt.sh <密钥> <原始nt_msg.db> [输出明文库路径]
set -e
KEY="$1"; SRC="$2"; OUT="${3:-nt_msg_plain.db}"
SAFE_KEY=$(printf '%s' "$KEY" | sed "s/'/''/g")

# 1) 剥掉前 1024 字节自定义头
tail -c +1025 "$SRC" > /tmp/nt_msg.clear.db

# 2) 解密导出（注意 PRAGMA 顺序: page_size 在 key 前, 其余在 key 后）
sqlcipher /tmp/nt_msg.clear.db << EOF
PRAGMA cipher_page_size = 4096;
PRAGMA key = '$SAFE_KEY';
PRAGMA kdf_iter = 4000;
PRAGMA cipher_hmac_algorithm = HMAC_SHA1;
PRAGMA cipher_kdf_algorithm = PBKDF2_HMAC_SHA512;
ATTACH DATABASE '$OUT' AS plain KEY '';
SELECT sqlcipher_export('plain');
DETACH DATABASE plain;
EOF
echo "完成: $OUT"
sqlite3 "$OUT" "SELECT count(*) FROM sqlite_master WHERE type='table';"
