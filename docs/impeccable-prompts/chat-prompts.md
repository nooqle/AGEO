# Chat Page Prompts

适用文件：

- `frontend/src/app/chat/[sessionId]/page.tsx`
- `frontend/src/components/chat/ChatPanel.tsx`
- `frontend/src/components/chat/InputArea.tsx`
- `frontend/src/components/chat/MessageList.tsx`
- `frontend/src/components/chat/responsive-chat-layout.tsx`
- `frontend/src/components/layout/ChatSidebar.tsx`
- `frontend/src/components/canvas/CanvasPanel.tsx`

## 1. 聊天工作台整体体验升级

```text
使用 impeccable-frontend-design 重做 Specta AI 聊天工作台的体验。

目标文件：
- frontend/src/app/chat/[sessionId]/page.tsx
- frontend/src/components/chat/ChatPanel.tsx
- frontend/src/components/chat/InputArea.tsx
- frontend/src/components/chat/MessageList.tsx
- frontend/src/components/chat/responsive-chat-layout.tsx
- frontend/src/components/layout/ChatSidebar.tsx
- frontend/src/components/canvas/CanvasPanel.tsx

业务目标：
- 让用户感觉这是一个可信、清晰、专业的多智能体分析工作台
- 减少复杂信息带来的压力
- 强化聊天区、状态区、Artifact 区之间的层级关系

约束：
- 保留现有核心交互模型：聊天 + 侧边栏 + canvas
- 不改 API 协议和状态管理逻辑
- 不用模板化 AI 聊天 UI

设计方向：
- professional + calm + editorial
- 重点提升布局节奏、信息层级、状态反馈和阅读舒适度

执行要求：
- 直接修改代码
- 如需调整组件关系，保持改动聚焦
- 最后说明你如何处理“复杂但不乱”的问题
```

## 2. 聊天页细节打磨

```text
使用 impeccable-polish 打磨聊天页，但不要重做交互结构。

目标文件：
- frontend/src/components/chat/ChatPanel.tsx
- frontend/src/components/chat/InputArea.tsx
- frontend/src/components/chat/MessageList.tsx
- frontend/src/components/chat/Message/*.tsx
- frontend/src/components/canvas/CanvasPanel.tsx

当前问题：
- 细节完成度不够高
- 间距、对齐、层级、视觉一致性可能存在瑕疵
- 某些状态块可能太重或太轻

要求：
- 不改信息架构
- 不新增复杂动画
- 重点修复 spacing、typography、按钮层级、状态块样式和滚动区域细节

输出要求：
- 直接改代码
- 最后列出修复了哪些具体细节问题
```

## 3. 聊天页复杂度审查

```text
使用 impeccable-audit 审查聊天页的体验质量，但先不要改代码。

范围：
- frontend/src/app/chat/[sessionId]/page.tsx
- frontend/src/components/chat/
- frontend/src/components/canvas/
- frontend/src/components/layout/ChatSidebar.tsx

重点：
- 复杂信息是否过载
- 不同消息类型是否足够可区分
- 输入区、状态区、执行区、结果区是否有明确视觉层级
- 移动端是否存在显著可用性风险
- 滚动、加载、空状态、断线重连提示是否清楚

输出要求：
- 按严重程度排序
- 每个问题说明影响范围和修复建议
- 标注哪些问题更适合后续用 impeccable-polish、impeccable-clarify 或 impeccable-harden 处理
```

## 4. 聊天页微动效增强

```text
使用 impeccable-animate 为聊天页增加有目的的动效。

目标文件：
- frontend/src/components/chat/MessageList.tsx
- frontend/src/components/chat/InputArea.tsx
- frontend/src/components/chat/ProgressIndicator.tsx
- frontend/src/components/canvas/CanvasPanel.tsx

要求：
- 动效必须服务状态理解和反馈
- 优先处理：消息进入、状态切换、加载反馈、面板展开收起
- 注意 reduced motion
- 不要引入花哨但无意义的动画
- 不要显著增加渲染压力

输出要求：
- 直接改代码
- 最后说明每个主要动效解决了什么体验问题
```

## 5. 聊天页稳健性增强

```text
使用 impeccable-harden 强化聊天页的稳健性和边界情况处理。

目标文件：
- frontend/src/app/chat/[sessionId]/page.tsx
- frontend/src/components/chat/
- frontend/src/components/canvas/

重点：
- 超长消息
- 空状态
- 执行中状态
- 错误状态
- 断线重连
- 移动端输入区挤压
- 多种消息块在窄屏下的溢出问题

要求：
- 直接修改代码
- 只做与稳健性和可用性相关的改动
- 最后明确列出处理了哪些边界情况
```
