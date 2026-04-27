# 域名归属识别与历史记忆设计

## 目标

A4 抓取结果里的引用域名需要被稳定识别为“网站名、主体平台、来源类型、与品牌的关系”。这些信息不能长期硬编码在报告模板或工具函数里，否则会变成无限补词典，也会让同一个域名在不同报告里漂移。

## 职责边界

代码只负责确定性动作：

- 从 URL 提取域名。
- 归一化 `www`、`m`、`mip`、`wap` 等机械前缀。
- 查历史库。
- 校验结构化结果。
- 写回历史库。
- 在本次 citation 上挂载结构化 metadata。

大模型负责语义判断：

- 域名对应的网站名。
- 网站归属主体。
- 来源类型：官网、权威媒体、垂直媒体、社区、内容平台、其他。
- 该域名与当前品牌的关系：官网、官方渠道、第三方渠道、无关、未知。
- 判断置信度和判断理由。
- 是否建议和某个主域合并，或者保留为独立子站。

历史库负责稳定复用：

- 同一个 canonical domain 只识别一次，后续复用。
- 品牌关系独立存储，避免“某域名对 A 品牌是官网”污染到其他品牌。
- 人工修正优先于模型判断；模型判断失败时写入明确的 `unresolved` 失败结果。

## 存储模型

`domain_identity_records` 存域名本体：

- `canonical_domain`
- `display_name`
- `owner_name`
- `source_type`
- `site_category`
- `confidence`
- `status`
- `resolved_by`
- `evidence_payload`

`brand_domain_relations` 存品牌关系：

- `entity_id`
- `brand_name`
- `canonical_domain`
- `relation_type`
- `confidence`
- `status`
- `resolved_by`
- `evidence_payload`

## 调用链

1. A4 抓取 citation，拿到 URL、domain、title、snippet、source/site_name。
2. 代码生成 canonical domain。
3. 查 `domain_identity_records` 和 `brand_domain_relations`。
4. 命中已解析记录：直接写入 citation metadata。
5. 未命中：A4 enrichment 同步调用模型 resolver。
6. 模型 resolver 按结构化 schema 写回历史库和本次 citation。
7. 模型失败：写入 `unresolved`，这是本次失败结果，不是异步待处理。
8. A5 报告只消费结构化 metadata，不在报告阶段猜网站归属。

## 明确不做

- 不在代码里持续维护“某域名是什么网站”的大词典。
- 不让 A5 报告模板临时判断网站归属。
- 不把“域名本体身份”和“对某品牌是否官网”混在一个字段里。
- 不设计无人消费的 `pending_llm` 状态。
