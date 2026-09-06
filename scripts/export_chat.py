#!/usr/bin/env python3
"""导出 QQ NT 私聊聊天记录为 txt + html。

用法: python3 export_chat.py <明文nt_msg.db> <我的uid> <对方uid> <对方昵称> <输出前缀>

示例: python3 export_chat.py nt_msg_plain.db u_AAAA... u_BBBB... 张三 ./chat
产出: <前缀>.txt 和 <前缀>.html
"""
import datetime
import html
import sqlite3
import sys

def read_varint(buf, i):
    v = 0; shift = 0
    while True:
        b = buf[i]; i += 1
        v |= (b & 0x7F) << shift
        if not (b & 0x80):
            return v, i
        shift += 7

def parse_fields(buf):
    i = 0
    while i < len(buf):
        try:
            key, i = read_varint(buf, i)
            fn, wt = key >> 3, key & 7
            if wt == 0:
                v, i = read_varint(buf, i)
                yield fn, wt, v
            elif wt == 2:
                ln, i = read_varint(buf, i)
                yield fn, wt, buf[i:i + ln]
                i += ln
            elif wt == 5:
                yield fn, wt, buf[i:i + 4]; i += 4
            elif wt == 1:
                yield fn, wt, buf[i:i + 8]; i += 8
            else:
                return
        except IndexError:
            return

def segment_summary(seg):
    """MsgContent 段 -> 可读文本"""
    text = None; etype = None; extras = []
    for fn, wt, v in parse_fields(seg):
        if fn == 45101 and wt == 2:
            text = v.decode("utf-8", "replace")
        elif fn == 45002 and wt == 0:
            etype = v
        elif wt == 2 and isinstance(v, (bytes, bytearray)) and len(v) >= 4:
            try:
                s = v.decode("utf-8")
                if s.isprintable():
                    extras.append(s)
            except UnicodeDecodeError:
                pass
    if text is not None:
        return text
    if etype == 2:
        return "[表情]"
    if etype in (3, 8):
        return "[图片]"
    if etype == 6:
        return "[文件]"
    if etype == 4:
        return "[语音]"
    for s in extras:
        low = s.lower()
        if any(ext in low for ext in (".zip", ".jpg", ".png", ".mp4", ".mp3",
                                      ".pdf", ".exe", ".apk", ".gif", ".rar")):
            return f"[文件] {s}"
    if extras:
        return "[" + " | ".join(extras[:2]) + "]"
    return f"[非文本消息 type={etype}]"

def parse_40800(blob):
    if blob is None:
        return ""
    segs = []
    for fn, wt, v in parse_fields(blob):
        if fn == 40800 and wt == 2:
            segs.append(segment_summary(v))
    return " ".join(segs).strip()

def main():
    db, my_uid, peer_uid, peer_name, prefix = sys.argv[1:6]
    me_name = "我"
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT [40020],[40050],[40800] FROM c2c_msg_table "
        "WHERE [40021]=? OR [40020]=? ORDER BY [40050] ASC",
        (peer_uid, peer_uid)).fetchall()

    txt, msgs, last_day = [], [], None
    for sender, ts, blob in rows:
        dt = datetime.datetime.fromtimestamp(ts)
        if dt.date() != last_day:
            last_day = dt.date()
            txt.append(f"\n===== {last_day.isoformat()} =====")
            msgs.append(f'<div class="day">{last_day.isoformat()}</div>')
        who = me_name if sender == my_uid else peer_name
        cls = "me" if sender == my_uid else "peer"
        content = parse_40800(blob) or "[无内容/已撤回]"
        t = dt.strftime("%H:%M:%S")
        txt.append(f"[{t}] {who}: {content}")
        msgs.append(
            f'<div class="msg {cls}"><div class="who">{html.escape(who)} {t}</div>'
            f'<div class="body">{html.escape(content)}</div></div>')

    with open(prefix + ".txt", "w") as f:
        f.write("\n".join(txt))
    with open(prefix + ".html", "w") as f:
        f.write("<!DOCTYPE html><html><head><meta charset='utf-8'>"
                f"<title>聊天记录 - {peer_name}</title><style>"
                "body{font-family:-apple-system,'PingFang SC',sans-serif;"
                "background:#f5f5f5;max-width:820px;margin:0 auto;padding:20px}"
                ".day{text-align:center;color:#888;margin:16px 0;font-size:13px}"
                ".msg{margin:8px 0;max-width:72%;padding:8px 12px;border-radius:12px;"
                "background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.06)}"
                ".msg .who{font-size:11px;color:#999;margin-bottom:3px}"
                ".msg .body{font-size:14px;white-space:pre-wrap;word-break:break-word}"
                ".me{margin-left:auto;background:#d2f0d2}"
                ".peer{margin-right:auto}</style></head><body>"
                f"<h2>与 {peer_name} 的聊天记录</h2>"
                f"<p style='color:#666'>共 {len(rows)} 条消息</p>"
                + "\n".join(msgs) + "</body></html>")
    print(f"完成: {len(rows)} 条消息 -> {prefix}.txt / {prefix}.html")

if __name__ == "__main__":
    main()
