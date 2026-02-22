## 实施步骤

### 第一阶段：安装依赖
1. 安装 `@remixicon/react` 包
2. 卸载 `lucide-react`（可选，视情况而定）

### 第二阶段：图标映射与替换
根据 lucide-react 图标映射到对应的 Remix Icon：

| Lucide Icon | Remix Icon |
|------------|-----------|
| Send | RiSendPlaneLine |
| User | RiUserLine |
| Settings | RiSettings4Line |
| History | RiHistoryLine |
| Plus | RiAddLine |
| X | RiCloseLine |
| Check | RiCheckLine |
| ChevronDown | RiArrowDownSLine |
| ChevronUp | RiArrowUpSLine |
| ChevronLeft | RiArrowLeftSLine |
| ChevronRight | RiArrowRightSLine |
| FileText | RiFileTextLine |
| Table | RiTableLine |
| Paperclip | RiAttachmentLine |
| Download | RiDownloadLine |
| Copy | RiFileCopyLine |
| Share2 | RiShareLine |
| Link | RiLinkLine |
| Loader2 | RiLoader4Line |
| AlertCircle | RiErrorWarningLine |
| CheckCircle | RiCheckboxCircleLine |
| Sparkles | RiSparklingLine |
| Bot | RiRobotLine |
| Brain | RiBrainLine |
| Eye | RiEyeLine |
| Clock | RiTimeLine |
| Edit3 | RiEditLine |
| Trash2 | RiDeleteBinLine |
| MoreHorizontal | RiMoreLine |
| MessageSquare | RiMessage3Line |
| ListTodo | RiListCheckLine |
| Zap | RiFlashlightLine |
| CheckSquare | RiCheckboxLine |
| Activity | RiPulseLine |
| ScanLine | RiScanLine |
| Play | RiPlayLine |
| Terminal | RiTerminalLine |
| Square | RiStopLine |
| Maximize2 | RiFullscreenLine |
| Minimize2 | RiFullscreenExitLine |
| Wrench | RiToolsLine |
| BarChart3 | RiBarChartBoxLine |
| Table2 | RiTableLine |
| Users | RiGroupLine |
| ArrowRight | RiArrowRightLine |
| Star | RiStarLine |
| Info | RiInformationLine |
| PanelRightClose | RiLayoutRightLine |

### 第三阶段：逐文件替换
需要修改的文件列表（共 20+ 个）：
1. `src/components/layout/Header.tsx`
2. `src/components/layout/ProjectSidebar.tsx`
3. `src/components/chat/InputArea.tsx`
4. `src/components/chat/SpectaChat.tsx`
5. `src/components/chat/TPAORCard.tsx`
6. `src/components/chat/TPAORBlock.tsx`
7. `src/components/chat/MiniProgress.tsx`
8. `src/components/chat/MinimaxChat.tsx`
9. `src/components/chat/AgentMessage.tsx`
10. `src/components/chat/AgentCallIndicator.tsx`
11. `src/components/chat/ConfirmationCard.tsx`
12. `src/components/chat/ProgressIndicator.tsx`
13. `src/components/chat/MessageActions.tsx`
14. `src/components/chat/Message/SystemMessage.tsx`
15. `src/components/chat/Message/ExecutionStepMessage.tsx`
16. `src/components/chat/Message/ConfirmationBlock.tsx`
17. `src/components/chat/Message/OutputCard.tsx`
18. `src/components/canvas/CanvasPanel.tsx`
19. `src/components/canvas/CanvasHeader.tsx`
20. `src/components/canvas/CanvasTabs.tsx`
21. `src/components/canvas/contents/SelectionContent.tsx`
22. `src/components/canvas/contents/DataTableContent.tsx`
23. `src/app/page.tsx`

### 第四阶段：验证
1. 运行 `npm run lint` 检查代码规范
2. 运行 `npm run build` 确保构建成功
3. 启动开发服务器验证图标显示效果

请确认这个计划后，我将开始执行具体的替换工作。