# 3c-C2 出口：rule-first + 稳定 prompt LLM 编译

日期：2026-07-21

## 行为

1. `compile-nl`：`allow_llm` 默认 true  
2. **先规则** `compile_nl_to_ops`（零费用、确定性）  
3. 规则 miss → **LLM**：system = `prompts/topology_ops_compiler.md` 全文；user = JSON(`instruction` + compact topology)  
4. 解析 JSON ops → 白名单过滤 → `apply_topology_ops` 结构校验 → 返回与 preview 同形  
5. 仍不写库；前端确认后 apply  

## 缓存布局

```
[system] topology_ops_compiler.md     ← 稳定前缀，少改
[user]   { instruction, topology }    ← 仅易变尾部
```

## 验证

- suite **79 passed**（含 `test_topology_nl_llm.py` mock）  
- tsc 0  

## 分拆 backlog

`docs/plans/2026-07-21-god-file-split-backlog.md`
