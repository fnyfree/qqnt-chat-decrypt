# 在 lldb 中执行：dump 所有可写内存段到 /tmp/qq_heap.bin + 索引
import lldb, struct

def dump_all(debugger, command, result, internal_dict):
    proc = debugger.GetSelectedTarget().GetProcess()
    err = lldb.SBError()
    out = open("/tmp/qq_heap.bin", "wb")
    idx = open("/tmp/qq_heap.idx", "w")
    addr = 0
    total = 0
    regions = 0
    region = lldb.SBMemoryRegionInfo()
    while True:
        sberr = proc.GetMemoryRegionInfo(addr, region)
        if sberr.Fail():
            break
        base = region.GetRegionBase()
        size = region.GetRegionEnd() - base
        if region.IsWritable() and size > 0:
            data = proc.ReadMemory(base, size, err)
            if data:
                off = out.tell()
                out.write(data)
                idx.write(f"{base:x} {size:x} {off:x}\n")
                total += len(data)
                regions += 1
        addr = region.GetRegionEnd()
        if addr == 0:
            break
    out.close(); idx.close()
    print("DUMPDONE regions=%d bytes=%d" % (regions, total))

def __lldb_init_module(debugger, internal_dict):
    debugger.HandleCommand("command script add -f dump_heap.dump_all dump-all")
