SearchInfo
搜索结果信息

被如下接口引用：ChatCompletions, GroupChatCompletions。

名称	类型	必选	描述
SearchResults	Array of SearchResult	否	搜索引文信息
注意：此字段可能返回 null，表示取不到有效值。
Mindmap	Mindmap	否	脑图（回复中不一定存在，流式协议中，仅在最后一条流式数据中返回）
注意：此字段可能返回 null，表示取不到有效值。
RelevantEvents	Array of RelevantEvent	否	相关事件（回复中不一定存在，流式协议中，仅在最后一条流式数据中返回，深度模式下返回）
注意：此字段可能返回 null，表示取不到有效值。
RelevantEntities	Array of RelevantEntity	否	相关组织及人物（回复中不一定存在，流式协议中，仅在最后一条流式数据中返回，深度模式下返回）
注意：此字段可能返回 null，表示取不到有效值。
Timeline	Array of Timeline	否	时间线（回复中不一定存在，流式协议中，仅在最后一条流式数据中返回，深度模式下返回）
注意：此字段可能返回 null，表示取不到有效值。
SupportDeepSearch	Boolean	否	是否命中搜索深度模式
注意：此字段可能返回 null，表示取不到有效值。
Outline	Array of String	否	搜索回复大纲（深度模式下返回）
注意：此字段可能返回 null，表示取不到有效值。