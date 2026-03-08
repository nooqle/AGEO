# Impeccable Prompt Templates

面向 Specta AI 项目的 Impeccable 提示词模板集合。

使用原则：

- 明确写出要使用的 skill，例如 `impeccable-frontend-design`
- 尽量写明目标文件、业务目标、设计方向和禁止改动范围
- 如果你想避免歧义，始终使用完整 skill 名，不要只写 `audit` 或 `polish`

建议优先顺序：

1. 大改版或首屏重做：`impeccable-frontend-design`
2. 先找问题：`impeccable-audit` 或 `impeccable-critique`
3. 已有页面细修：`impeccable-polish`
4. 风格太平：`impeccable-bolder`
5. 风格太吵：`impeccable-quieter`
6. 动效增强：`impeccable-animate`
7. 移动端适配：`impeccable-adapt`
8. 边界情况和稳健性：`impeccable-harden`

模板索引：

- `homepage-prompts.md`: 首页与 landing 相关模板
- `chat-prompts.md`: 聊天页与对话工作台模板
- `dashboard-prompts.md`: Dashboard 与监控台模板

常用短模板：

```text
使用 impeccable-<skill-name> 处理 <目标文件或页面>。

目标：
- <业务目标>
- <体验目标>

约束：
- 保留 <不能动的内容>
- 不要修改 <明确禁止改动>
- 风格方向：<风格关键词>

执行要求：
- 直接修改代码
- 说明关键设计决策
- 运行相关验证；如果不能运行，明确说明
```
