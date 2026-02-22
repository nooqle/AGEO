# 任务：实现生产级 Chat 页面组件

## 背景
基于《AEO 智能分析助手 - 前端交互设计文档 v2.0》，实现完整的对话区组件，包括消息展示、TPAOR 状态、输入区域、进度指示、浏览器状态提示等。

## 设计要求回顾

### 核心原则
1. **对话为主** - 对话区是主视觉中心
2. **渐进展示** - Agent 执行过程透明可见，TPAOR 状态实时更新
3. **双通道交互** - 用户可在对话或 Canvas 中完成确认操作
4. **可回溯控制** - 支持停止执行、回退重发

### 布局状态
- **纯对话态**: 对话区 100% 居中 (max-width: 800px)
- **分栏态**: 对话区 50% + Canvas 50%
- **聚焦态**: 对话区 35% + Canvas 65%

## 目录结构
```
frontend/src/
├── components/
│   └── chat/
│       ├── index.ts                    # 统一导出
│       ├── ChatPanel.tsx               # 主容器
│       ├── MessageList.tsx             # 消息列表（含虚拟滚动）
│       ├── Message/
│       │   ├── index.tsx               # 消息分发组件
│       │   ├── UserMessage.tsx         # 用户消息
│       │   ├── AgentMessage.tsx        # Agent 消息（含 TPAOR、卡片、确认）
│       │   ├── SystemMessage.tsx       # 系统消息
│       │   ├── TPAORBlock.tsx          # TPAOR 展示块（可折叠）
│       │   ├── OutputCard.tsx          # 产出内容卡片
│       │   └── ConfirmationBlock.tsx   # 确认请求块
│       ├── InputArea.tsx               # 输入区域
│       ├── ProgressIndicator.tsx       # 执行进度指示器
│       ├── BrowserStateAlert.tsx       # 浏览器状态提示
│       ├── StopExecutionStatus.tsx     # 停止执行状态
│       └── MessageActions.tsx          # 消息操作菜单
│
├── stores/
│   └── conversationStore.ts            # 对话状态管理
│
├── hooks/
│   └── useWebSocket.ts                 # WebSocket 连接
│
├── types/
│   ├── message.ts                      # 消息类型定义
│   └── agent.ts                        # Agent 相关类型
│
└── lib/
    ├── utils.ts                        # 工具函数
    └── cn.ts                           # className 合并
```

## 文件实现

### 1. 类型定义

#### types/message.ts
```typescript
// frontend/src/types/message.ts

export type MessageType = 'user' | 'agent' | 'system';
export type MessageStatus = 'sending' | 'sent' | 'error';

export interface TPAORContent {
  thought?: string;
  plan?: string;
  action?: string;
  observation?: string;
  response?: string;
}

export interface OutputCard {
  id: string;
  type: 'report' | 'chart' | 'dataTable' | 'selection';
  title: string;
  preview: {
    metrics?: Record<string, string | number>;
    description?: string;
    itemCount?: number;
  };
}

export interface ConfirmationOption {
  id: string;
  label: string;
  description?: string;
  icon?: string;
  recommended?: boolean;
}

export interface ConfirmationRequest {
  requestId: string;
  type: 'brand_info' | 'persona_selection' | 'action_choice' | 'continue';
  message: string;
  options: ConfirmationOption[];
  allowTextInput: boolean;
  timeout?: number;
}

export interface MessageMetadata {
  canEdit: boolean;
  canRollback: boolean;
  relatedOutputIds: string[];
  executionTime?: number;
}

export interface Message {
  id: string;
  type: MessageType;
  content: string;
  timestamp: Date;
  status?: MessageStatus;
  
  // Agent 消息特有
  tpaor?: TPAORContent;
  outputCards?: OutputCard[];
  confirmationRequest?: ConfirmationRequest;
  
  // 元数据
  metadata: MessageMetadata;
}
```

#### types/agent.ts
```typescript
// frontend/src/types/agent.ts

export type TPAORPhase = 'thought' | 'plan' | 'action' | 'observation' | 'response';

export interface TPAORUpdate {
  phase: TPAORPhase;
  content: string;
  isComplete: boolean;
  timestamp: Date;
}

export interface SubTask {
  id: string;
  name: string;
  platform?: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress?: number;
  message?: string;
}

export interface ExecutionProgress {
  stage: string;
  stageName: string;
  stageIndex: number;
  totalStages: number;
  progress: number; // 0-1
  status: 'pending' | 'running' | 'completed' | 'failed';
  details?: string;
  subTasks?: SubTask[];
  estimatedTimeRemaining?: number;
}

export type BrowserStateType = 
  | 'idle'
  | 'initializing'
  | 'navigating'
  | 'checking_login'
  | 'waiting_for_login'
  | 'logged_in'
  | 'enabling_search'
  | 'submitting'
  | 'waiting_response'
  | 'extracting'
  | 'completed'
  | 'error';

export interface BrowserState {
  state: BrowserStateType;
  platform: 'kimi' | 'deepseek';
  message: string;
  requiresAction: boolean;
  actionHint?: string;
  progress?: number;
}

export interface StopState {
  isStopped: boolean;
  stoppedAt: Date;
  completedStages: Array<{
    name: string;
    description?: string;
    completedAt: Date;
  }>;
  pendingStages: Array<{
    name: string;
    description?: string;
  }>;
  partialResults?: {
    fetchedCount: number;
    totalCount: number;
    platforms: Record<string, { completed: number; total: number }>;
  };
  canResume: boolean;
  canRetry: boolean;
}
```

### 2. 工具函数

#### lib/cn.ts
```typescript
// frontend/src/lib/cn.ts
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

#### lib/utils.ts
```typescript
// frontend/src/lib/utils.ts

// 格式化时间 (10:30)
export function formatTime(date: Date): string {
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

// 格式化日期时间 (1月28日 10:30)
export function formatDateTime(date: Date): string {
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

// 格式化进度
export function formatProgress(progress: number): string {
  return `${Math.round(progress * 100)}%`;
}

// 格式化剩余时间
export function formatTimeRemaining(seconds: number): string {
  if (seconds < 60) return `约 ${seconds} 秒`;
  const minutes = Math.ceil(seconds / 60);
  return `约 ${minutes} 分钟`;
}

// 获取带圈数字
export function getCircledNumber(n: number): string {
  const circled = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨', '⑩'];
  return circled[n - 1] || String(n);
}

// 解析用户选择（支持 "①②" "1,2" "1和2" "选择1和2"）
export function parseUserSelection(input: string): string[] | null {
  const circledMap: Record<string, string> = {
    '①': '1', '②': '2', '③': '3', '④': '4', '⑤': '5',
    '⑥': '6', '⑦': '7', '⑧': '8', '⑨': '9', '⑩': '10',
  };
  
  let normalized = input;
  Object.entries(circledMap).forEach(([circled, num]) => {
    normalized = normalized.replace(new RegExp(circled, 'g'), num);
  });
  
  const matches = normalized.match(/\d+/g);
  if (!matches) return null;
  
  return [...new Set(matches)];
}

// 截断文本
export function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength - 3) + '...';
}

// 生成唯一 ID
export function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}
```

### 3. 状态管理

#### stores/conversationStore.ts
```typescript
// frontend/src/stores/conversationStore.ts
import { create } from 'zustand';
import { Message, ConfirmationRequest } from '@/types/message';
import { TPAORUpdate, ExecutionProgress, BrowserState, StopState } from '@/types/agent';
import { generateId } from '@/lib/utils';

interface CurrentTPAOR {
  thought: string;
  plan: string;
  action: string;
  observation: string;
  activePhase: 'thought' | 'plan' | 'action' | 'observation' | null;
}

interface ConversationState {
  // 消息
  messages: Message[];
  
  // 执行状态
  isAgentExecuting: boolean;
  executionStartTime: Date | null;
  
  // TPAOR 状态
  currentTPAOR: CurrentTPAOR;
  
  // 执行进度
  executionProgress: ExecutionProgress | null;
  
  // 浏览器状态
  browserState: BrowserState | null;
  
  // 停止状态
  stopState: StopState | null;
  
  // 确认请求
  pendingConfirmation: ConfirmationRequest | null;
  
  // Actions
  addMessage: (message: Omit<Message, 'id' | 'timestamp' | 'metadata'> & Partial<Pick<Message, 'metadata'>>) => string;
  updateMessage: (id: string, updates: Partial<Message>) => void;
  removeMessage: (id: string) => void;
  
  updateTPAOR: (update: TPAORUpdate) => void;
  resetTPAOR: () => void;
  
  setExecutionProgress: (progress: ExecutionProgress | null) => void;
  setBrowserState: (state: BrowserState | null) => void;
  setStopState: (state: StopState | null) => void;
  setPendingConfirmation: (request: ConfirmationRequest | null) => void;
  
  startExecution: () => void;
  stopExecution: () => void;
  
  clearMessagesAfter: (messageId: string) => Message[];
  reset: () => void;
}

const initialTPAOR: CurrentTPAOR = {
  thought: '',
  plan: '',
  action: '',
  observation: '',
  activePhase: null,
};

export const useConversationStore = create<ConversationState>((set, get) => ({
  messages: [],
  isAgentExecuting: false,
  executionStartTime: null,
  currentTPAOR: initialTPAOR,
  executionProgress: null,
  browserState: null,
  stopState: null,
  pendingConfirmation: null,
  
  addMessage: (messageData) => {
    const id = generateId();
    const message: Message = {
      id,
      timestamp: new Date(),
      metadata: {
        canEdit: messageData.type === 'user',
        canRollback: true,
        relatedOutputIds: [],
      },
      ...messageData,
    };
    
    set((state) => ({
      messages: [...state.messages, message],
    }));
    
    return id;
  },
  
  updateMessage: (id, updates) => {
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === id ? { ...m, ...updates } : m
      ),
    }));
  },
  
  removeMessage: (id) => {
    set((state) => ({
      messages: state.messages.filter((m) => m.id !== id),
    }));
  },
  
  updateTPAOR: (update) => {
    set((state) => ({
      currentTPAOR: {
        ...state.currentTPAOR,
        [update.phase]: update.content,
        activePhase: update.isComplete ? null : update.phase,
      },
    }));
  },
  
  resetTPAOR: () => {
    set({ currentTPAOR: initialTPAOR });
  },
  
  setExecutionProgress: (progress) => {
    set({ executionProgress: progress });
  },
  
  setBrowserState: (browserState) => {
    set({ browserState });
  },
  
  setStopState: (stopState) => {
    set({ stopState });
  },
  
  setPendingConfirmation: (request) => {
    set({ pendingConfirmation: request });
  },
  
  startExecution: () => {
    set({
      isAgentExecuting: true,
      executionStartTime: new Date(),
      currentTPAOR: initialTPAOR,
      stopState: null,
      executionProgress: null,
    });
  },
  
  stopExecution: () => {
    set({
      isAgentExecuting: false,
      browserState: null,
    });
  },
  
  clearMessagesAfter: (messageId) => {
    const { messages } = get();
    const index = messages.findIndex((m) => m.id === messageId);
    if (index === -1) return [];
    
    const removed = messages.slice(index + 1);
    set({ messages: messages.slice(0, index + 1) });
    return removed;
  },
  
  reset: () => {
    set({
      messages: [],
      isAgentExecuting: false,
      executionStartTime: null,
      currentTPAOR: initialTPAOR,
      executionProgress: null,
      browserState: null,
      stopState: null,
      pendingConfirmation: null,
    });
  },
}));
```

### 4. Chat 组件

#### components/chat/ChatPanel.tsx
```typescript
// frontend/src/components/chat/ChatPanel.tsx
'use client';

import { useRef, useEffect } from 'react';
import { useConversationStore } from '@/stores/conversationStore';
import { MessageList } from './MessageList';
import { InputArea } from './InputArea';
import { ProgressIndicator } from './ProgressIndicator';
import { BrowserStateAlert } from './BrowserStateAlert';
import { StopExecutionStatus } from './StopExecutionStatus';
import { cn } from '@/lib/cn';

interface ChatPanelProps {
  sessionId: string;
  className?: string;
}

export function ChatPanel({ sessionId, className }: ChatPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  
  const {
    messages,
    isAgentExecuting,
    currentTPAOR,
    executionProgress,
    browserState,
    stopState,
    pendingConfirmation,
    addMessage,
    startExecution,
    stopExecution,
    setPendingConfirmation,
  } = useConversationStore();
  
  // 自动滚动到底部
  useEffect(() => {
    if (scrollRef.current) {
      const { scrollHeight, clientHeight, scrollTop } = scrollRef.current;
      const isNearBottom = scrollHeight - clientHeight - scrollTop < 100;
      
      if (isNearBottom || isAgentExecuting) {
        scrollRef.current.scrollTo({
          top: scrollRef.current.scrollHeight,
          behavior: 'smooth',
        });
      }
    }
  }, [messages, currentTPAOR, executionProgress, isAgentExecuting]);
  
  // 发送消息
  const handleSendMessage = (content: string) => {
    // 添加用户消息
    addMessage({
      type: 'user',
      content,
    });
    
    // 开始执行（模拟，实际通过 WebSocket）
    startExecution();
    
    // 模拟 Agent 响应
    simulateAgentResponse(content);
  };
  
  // 停止执行
  const handleStopExecution = () => {
    stopExecution();
    // TODO: 通过 WebSocket 发送停止命令
  };
  
  // 发送确认
  const handleConfirmation = (optionId: string) => {
    if (!pendingConfirmation) return;
    
    const option = pendingConfirmation.options.find(o => o.id === optionId);
    if (option) {
      addMessage({
        type: 'user',
        content: option.label,
      });
    }
    
    setPendingConfirmation(null);
    // TODO: 通过 WebSocket 发送确认
  };
  
  // 模拟 Agent 响应（开发调试用）
  const simulateAgentResponse = (userInput: string) => {
    const { updateTPAOR, setExecutionProgress, addMessage: addMsg, stopExecution: stop } = useConversationStore.getState();
    
    setTimeout(() => {
      updateTPAOR({
        phase: 'thought',
        content: `用户想要分析「${userInput}」品牌，我需要先收集品牌基础信息，然后进行竞品分析...`,
        isComplete: false,
        timestamp: new Date(),
      });
    }, 500);
    
    setTimeout(() => {
      updateTPAOR({
        phase: 'thought',
        content: `用户想要分析「${userInput}」品牌，我需要先收集品牌基础信息，然后进行竞品分析...`,
        isComplete: true,
        timestamp: new Date(),
      });
      updateTPAOR({
        phase: 'plan',
        content: `执行计划：\n1. 品牌信息采集\n2. 竞品识别分析\n3. 基准问题生成\n4. AI 答案抓取\n5. 数据分析与报告`,
        isComplete: false,
        timestamp: new Date(),
      });
    }, 1500);
    
    setTimeout(() => {
      updateTPAOR({
        phase: 'plan',
        content: `执行计划：\n1. 品牌信息采集\n2. 竞品识别分析\n3. 基准问题生成\n4. AI 答案抓取\n5. 数据分析与报告`,
        isComplete: true,
        timestamp: new Date(),
      });
      updateTPAOR({
        phase: 'action',
        content: `正在调用品牌竞品分析 Agent...`,
        isComplete: false,
        timestamp: new Date(),
      });
      setExecutionProgress({
        stage: 'brand_analysis',
        stageName: '品牌信息采集',
        stageIndex: 1,
        totalStages: 5,
        progress: 0.2,
        status: 'running',
      });
    }, 2500);
    
    setTimeout(() => {
      setExecutionProgress({
        stage: 'brand_analysis',
        stageName: '品牌信息采集',
        stageIndex: 1,
        totalStages: 5,
        progress: 0.8,
        status: 'running',
        subTasks: [
          { id: '1', name: '搜索品牌信息', status: 'completed' },
          { id: '2', name: '提取品牌属性', status: 'running' },
          { id: '3', name: '识别竞品', status: 'pending' },
        ],
      });
    }, 4000);
    
    setTimeout(() => {
      stop();
      setExecutionProgress(null);
      
      addMsg({
        type: 'agent',
        content: `我已完成对「${userInput}」品牌的初步分析。\n\n**品牌信息**\n- 品类：香氛/生活方式\n- 定位：东方美学高端香氛\n- 主要竞品：野兽派、祖玛珑、蒂普提克\n\n请确认以上信息是否正确？`,
        outputCards: [
          {
            id: 'report-1',
            type: 'report',
            title: '品牌基础分析报告',
            preview: {
              metrics: {
                '品牌': userInput,
                '品类': '香氛',
                '竞品数': 3,
              },
            },
          },
        ],
        confirmationRequest: {
          requestId: 'confirm-1',
          type: 'brand_info',
          message: '请确认品牌信息是否正确',
          options: [
            { id: 'confirm', label: '确认正确', recommended: true },
            { id: 'edit', label: '需要修改' },
          ],
          allowTextInput: true,
        },
      });
      
      useConversationStore.getState().setPendingConfirmation({
        requestId: 'confirm-1',
        type: 'brand_info',
        message: '请确认品牌信息是否正确',
        options: [
          { id: 'confirm', label: '确认正确', recommended: true },
          { id: 'edit', label: '需要修改' },
        ],
        allowTextInput: true,
      });
      
      useConversationStore.getState().resetTPAOR();
    }, 6000);
  };
  
  return (
    <div className={cn('flex flex-col h-full bg-white', className)}>
      {/* 消息列表 */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto scroll-smooth"
      >
        <div className="max-w-3xl mx-auto px-4 py-6">
          <MessageList
            messages={messages}
            onConfirmation={handleConfirmation}
          />
          
          {/* 执行进度 */}
          {isAgentExecuting && (
            <ProgressIndicator
              tpaor={currentTPAOR}
              progress={executionProgress}
              className="mt-4"
            />
          )}
          
          {/* 浏览器状态提示 */}
          {browserState?.requiresAction && (
            <BrowserStateAlert
              state={browserState}
              className="mt-4"
            />
          )}
          
          {/* 停止状态 */}
          {stopState?.isStopped && (
            <StopExecutionStatus
              state={stopState}
              onResume={() => {/* TODO */}}
              onRetry={() => {/* TODO */}}
              onSave={() => {/* TODO */}}
              className="mt-4"
            />
          )}
        </div>
      </div>
      
      {/* 输入区域 */}
      <InputArea
        onSend={handleSendMessage}
        onStop={handleStopExecution}
        isExecuting={isAgentExecuting}
        disabled={stopState?.isStopped}
        pendingConfirmation={pendingConfirmation}
        onConfirmation={handleConfirmation}
      />
    </div>
  );
}
```

#### components/chat/MessageList.tsx
```typescript
// frontend/src/components/chat/MessageList.tsx
'use client';

import { Message as MessageType } from '@/types/message';
import { Message } from './Message';
import { cn } from '@/lib/cn';

interface MessageListProps {
  messages: MessageType[];
  onConfirmation?: (optionId: string) => void;
  className?: string;
}

export function MessageList({ messages, onConfirmation, className }: MessageListProps) {
  if (messages.length === 0) {
    return <EmptyState />;
  }
  
  return (
    <div className={cn('space-y-4', className)}>
      {messages.map((message, index) => (
        <Message
          key={message.id}
          message={message}
          isLast={index === messages.length - 1}
          onConfirmation={onConfirmation}
        />
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-20 px-4">
      <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center mb-6 shadow-lg">
        <span className="text-4xl">🔍</span>
      </div>
      
      <h2 className="text-2xl font-bold text-gray-900 mb-2 text-center">
        欢迎使用 AEO 智能分析
      </h2>
      
      <p className="text-gray-500 text-center mb-8 max-w-md">
        输入品牌名称，AI 将自动分析该品牌在主流 AI 平台的声量表现，并生成优化建议
      </p>
      
      <div className="flex flex-wrap justify-center gap-2">
        {[
          { name: '观夏', emoji: '🌸' },
          { name: '野兽派', emoji: '🌹' },
          { name: '蕉内', emoji: '👕' },
          { name: '瑞幸咖啡', emoji: '☕' },
        ].map((brand) => (
          <button
            key={brand.name}
            onClick={() => {
              const input = document.querySelector('textarea');
              if (input) {
                (input as HTMLTextAreaElement).value = brand.name;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.focus();
              }
            }}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-full border border-gray-200 bg-white text-sm text-gray-700 hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700 transition-all shadow-sm"
          >
            <span>{brand.emoji}</span>
            <span>{brand.name}</span>
          </button>
        ))}
      </div>
      
      <div className="mt-12 grid grid-cols-3 gap-8 text-center">
        {[
          { icon: '📊', title: '声量分析', desc: '多平台数据采集' },
          { icon: '👥', title: '画像洞察', desc: '精准用户分析' },
          { icon: '📈', title: '优化建议', desc: '可落地执行方案' },
        ].map((feature) => (
          <div key={feature.title} className="text-gray-500">
            <div className="text-2xl mb-2">{feature.icon}</div>
            <div className="font-medium text-gray-700">{feature.title}</div>
            <div className="text-xs">{feature.desc}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

#### components/chat/Message/index.tsx
```typescript
// frontend/src/components/chat/Message/index.tsx
'use client';

import { useState } from 'react';
import { Message as MessageType } from '@/types/message';
import { UserMessage } from './UserMessage';
import { AgentMessage } from './AgentMessage';
import { SystemMessage } from './SystemMessage';
import { MessageActions } from '../MessageActions';
import { cn } from '@/lib/cn';

interface MessageProps {
  message: MessageType;
  isLast?: boolean;
  onConfirmation?: (optionId: string) => void;
}

export function Message({ message, isLast, onConfirmation }: MessageProps) {
  const [showActions, setShowActions] = useState(false);
  
  const renderMessage = () => {
    switch (message.type) {
      case 'user':
        return <UserMessage message={message} />;
      case 'agent':
        return (
          <AgentMessage
            message={message}
            onConfirmation={onConfirmation}
          />
        );
      case 'system':
        return <SystemMessage message={message} />;
      default:
        return null;
    }
  };
  
  return (
    <div
      className={cn(
        'group relative',
        message.type === 'user' ? 'flex justify-end' : ''
      )}
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
    >
      {renderMessage()}
      
      {/* 操作菜单 */}
      {showActions && message.metadata?.canRollback && (
        <MessageActions
          message={message}
          className={cn(
            'absolute top-0',
            message.type === 'user' ? 'left-0 -translate-x-full pr-2' : 'right-0 translate-x-full pl-2'
          )}
        />
      )}
    </div>
  );
}
```

#### components/chat/Message/UserMessage.tsx
```typescript
// frontend/src/components/chat/Message/UserMessage.tsx
'use client';

import { Message } from '@/types/message';
import { formatTime } from '@/lib/utils';
import { cn } from '@/lib/cn';

interface UserMessageProps {
  message: Message;
}

export function UserMessage({ message }: UserMessageProps) {
  return (
    <div className="max-w-[85%] md:max-w-[70%]">
      <div className="bg-indigo-600 text-white rounded-2xl rounded-tr-md px-4 py-3 shadow-sm">
        <div className="whitespace-pre-wrap break-words">
          {message.content}
        </div>
      </div>
      <div className="text-xs text-gray-400 mt-1 text-right">
        {formatTime(message.timestamp)}
      </div>
    </div>
  );
}
```

#### components/chat/Message/AgentMessage.tsx
```typescript
// frontend/src/components/chat/Message/AgentMessage.tsx
'use client';

import { Message } from '@/types/message';
import { TPAORBlock } from './TPAORBlock';
import { OutputCard } from './OutputCard';
import { ConfirmationBlock } from './ConfirmationBlock';
import { formatTime } from '@/lib/utils';
import { cn } from '@/lib/cn';

interface AgentMessageProps {
  message: Message;
  onConfirmation?: (optionId: string) => void;
}

export function AgentMessage({ message, onConfirmation }: AgentMessageProps) {
  const hasTpaor = message.tpaor && Object.values(message.tpaor).some(v => v);
  
  return (
    <div className="flex gap-3 max-w-[90%]">
      {/* Agent 头像 */}
      <div className="flex-shrink-0">
        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-sm">
          <span className="text-white text-sm font-medium">A</span>
        </div>
      </div>
      
      {/* 消息内容 */}
      <div className="flex-1 min-w-0">
        {/* 时间 */}
        <div className="text-xs text-gray-400 mb-1">
          {formatTime(message.timestamp)}
        </div>
        
        {/* TPAOR 块 */}
        {hasTpaor && (
          <div className="space-y-2 mb-3">
            {message.tpaor?.thought && (
              <TPAORBlock
                phase="thought"
                content={message.tpaor.thought}
                defaultExpanded={false}
              />
            )}
            {message.tpaor?.plan && (
              <TPAORBlock
                phase="plan"
                content={message.tpaor.plan}
                defaultExpanded={false}
              />
            )}
            {message.tpaor?.action && (
              <TPAORBlock
                phase="action"
                content={message.tpaor.action}
                defaultExpanded={true}
              />
            )}
          </div>
        )}
        
        {/* 文本内容 */}
        {message.content && (
          <div className="bg-gray-100 rounded-2xl rounded-tl-md px-4 py-3">
            <div className="prose prose-sm max-w-none text-gray-900 whitespace-pre-wrap break-words">
              {message.content}
            </div>
          </div>
        )}
        
        {/* 产出卡片 */}
        {message.outputCards && message.outputCards.length > 0 && (
          <div className="mt-3 space-y-2">
            {message.outputCards.map((card) => (
              <OutputCard key={card.id} card={card} />
            ))}
          </div>
        )}
        
        {/* 确认请求 */}
        {message.confirmationRequest && (
          <ConfirmationBlock
            request={message.confirmationRequest}
            onSelect={onConfirmation}
            className="mt-3"
          />
        )}
      </div>
    </div>
  );
}
```

#### components/chat/Message/TPAORBlock.tsx
```typescript
// frontend/src/components/chat/Message/TPAORBlock.tsx
'use client';

import { useState } from 'react';
import { ChevronDown, Brain, ListTodo, Zap, Eye, MessageSquare, Loader2 } from 'lucide-react';
import { cn } from '@/lib/cn';

interface TPAORBlockProps {
  phase: 'thought' | 'plan' | 'action' | 'observation' | 'response';
  content: string;
  isActive?: boolean;
  isComplete?: boolean;
  defaultExpanded?: boolean;
  progress?: number;
}

const phaseConfig = {
  thought: {
    icon: Brain,
    label: '思考',
    activeLabel: '正在思考...',
    colors: {
      bg: 'bg-purple-50',
      border: 'border-purple-200',
      text: 'text-purple-700',
      icon: 'text-purple-500',
    },
  },
  plan: {
    icon: ListTodo,
    label: '规划',
    activeLabel: '正在规划...',
    colors: {
      bg: 'bg-blue-50',
      border: 'border-blue-200',
      text: 'text-blue-700',
      icon: 'text-blue-500',
    },
  },
  action: {
    icon: Zap,
    label: '执行',
    activeLabel: '正在执行...',
    colors: {
      bg: 'bg-amber-50',
      border: 'border-amber-200',
      text: 'text-amber-700',
      icon: 'text-amber-500',
    },
  },
  observation: {
    icon: Eye,
    label: '观察',
    activeLabel: '正在观察...',
    colors: {
      bg: 'bg-green-50',
      border: 'border-green-200',
      text: 'text-green-700',
      icon: 'text-green-500',
    },
  },
  response: {
    icon: MessageSquare,
    label: '回复',
    activeLabel: '正在生成回复...',
    colors: {
      bg: 'bg-gray-50',
      border: 'border-gray-200',
      text: 'text-gray-700',
      icon: 'text-gray-500',
    },
  },
};

export function TPAORBlock({
  phase,
  content,
  isActive = false,
  isComplete = true,
  defaultExpanded = false,
  progress,
}: TPAORBlockProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded || isActive);
  const config = phaseConfig[phase];
  const Icon = config.icon;
  
  return (
    <div
      className={cn(
        'rounded-xl border overflow-hidden transition-all',
        config.colors.bg,
        config.colors.border,
        isActive && 'ring-2 ring-offset-1',
        isActive && phase === 'thought' && 'ring-purple-300',
        isActive && phase === 'plan' && 'ring-blue-300',
        isActive && phase === 'action' && 'ring-amber-300',
      )}
    >
      {/* 标题栏 */}
      <button
        className="w-full flex items-center justify-between px-3 py-2.5 hover:bg-black/5 transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2">
          {isActive ? (
            <Loader2 className={cn('w-4 h-4 animate-spin', config.colors.icon)} />
          ) : (
            <Icon className={cn('w-4 h-4', config.colors.icon)} />
          )}
          <span className={cn('text-sm font-medium', config.colors.text)}>
            {isActive ? config.activeLabel : config.label}
          </span>
        </div>
        <ChevronDown
          className={cn(
            'w-4 h-4 text-gray-400 transition-transform duration-200',
            isExpanded && 'rotate-180'
          )}
        />
      </button>
      
      {/* 内容区 */}
      <div
        className={cn(
          'overflow-hidden transition-all duration-200',
          isExpanded ? 'max-h-96' : 'max-h-0'
        )}
      >
        <div className="px-3 pb-3">
          <div className={cn('text-sm whitespace-pre-wrap', config.colors.text)}>
            {content}
          </div>
          
          {/* 进度条 */}
          {typeof progress === 'number' && (
            <div className="mt-3">
              <div className="h-1.5 bg-white/50 rounded-full overflow-hidden">
                <div
                  className={cn(
                    'h-full rounded-full transition-all duration-300',
                    phase === 'action' && 'bg-amber-500',
                  )}
                  style={{ width: `${progress * 100}%` }}
                />
              </div>
              <div className="text-xs text-gray-500 mt-1 text-right">
                {Math.round(progress * 100)}%
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
```

#### components/chat/Message/OutputCard.tsx
```typescript
// frontend/src/components/chat/Message/OutputCard.tsx
'use client';

import { FileText, BarChart3, Table2, Users, ArrowRight } from 'lucide-react';
import { OutputCard as OutputCardType } from '@/types/message';
import { useCanvasStore } from '@/stores/canvasStore';
import { cn } from '@/lib/cn';

interface OutputCardProps {
  card: OutputCardType;
}

const typeConfig = {
  report: {
    icon: FileText,
    label: '分析报告',
    colors: {
      bg: 'bg-indigo-50 hover:bg-indigo-100',
      border: 'border-indigo-200 hover:border-indigo-300',
      icon: 'text-indigo-600',
      title: 'text-indigo-900',
    },
  },
  chart: {
    icon: BarChart3,
    label: '数据图表',
    colors: {
      bg: 'bg-emerald-50 hover:bg-emerald-100',
      border: 'border-emerald-200 hover:border-emerald-300',
      icon: 'text-emerald-600',
      title: 'text-emerald-900',
    },
  },
  dataTable: {
    icon: Table2,
    label: '数据表格',
    colors: {
      bg: 'bg-blue-50 hover:bg-blue-100',
      border: 'border-blue-200 hover:border-blue-300',
      icon: 'text-blue-600',
      title: 'text-blue-900',
    },
  },
  selection: {
    icon: Users,
    label: '选择确认',
    colors: {
      bg: 'bg-purple-50 hover:bg-purple-100',
      border: 'border-purple-200 hover:border-purple-300',
      icon: 'text-purple-600',
      title: 'text-purple-900',
    },
  },
};

export function OutputCard({ card }: OutputCardProps) {
  const { openCanvas } = useCanvasStore();
  const config = typeConfig[card.type];
  const Icon = config.icon;
  
  const handleClick = () => {
    openCanvas({
      id: card.id,
      type: card.type,
      title: card.title,
      data: card.preview,
      createdAt: new Date(),
      relatedMessageId: '',
    });
  };
  
  return (
    <button
      onClick={handleClick}
      className={cn(
        'w-full text-left rounded-xl border p-4 transition-all',
        'hover:shadow-md cursor-pointer group',
        config.colors.bg,
        config.colors.border,
      )}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className={cn('p-1.5 rounded-lg bg-white/60', config.colors.icon)}>
            <Icon className="w-4 h-4" />
          </div>
          <div>
            <div className={cn('font-medium', config.colors.title)}>
              {card.title}
            </div>
            <div className="text-xs text-gray-500">{config.label}</div>
          </div>
        </div>
        <ArrowRight className="w-4 h-4 text-gray-400 group-hover:translate-x-1 transition-transform" />
      </div>
      
      {/* 预览指标 */}
      {card.preview?.metrics && (
        <div className="grid grid-cols-3 gap-2">
          {Object.entries(card.preview.metrics).slice(0, 3).map(([key, value]) => (
            <div key={key} className="bg-white/60 rounded-lg px-2 py-1.5">
              <div className="text-xs text-gray-500">{key}</div>
              <div className="font-medium text-gray-900 truncate">{String(value)}</div>
            </div>
          ))}
        </div>
      )}
      
      {/* 描述 */}
      {card.preview?.description && (
        <p className="text-sm text-gray-600 mt-2 line-clamp-2">
          {card.preview.description}
        </p>
      )}
    </button>
  );
}
```

#### components/chat/Message/ConfirmationBlock.tsx
```typescript
// frontend/src/components/chat/Message/ConfirmationBlock.tsx
'use client';

import { Clock, CheckCircle2 } from 'lucide-react';
import { ConfirmationRequest } from '@/types/message';
import { cn } from '@/lib/cn';

interface ConfirmationBlockProps {
  request: ConfirmationRequest;
  onSelect?: (optionId: string) => void;
  className?: string;
}

export function ConfirmationBlock({ request, onSelect, className }: ConfirmationBlockProps) {
  return (
    <div
      className={cn(
        'rounded-xl border border-amber-200 bg-gradient-to-br from-amber-50 to-orange-50 p-4',
        className
      )}
    >
      {/* 标题 */}
      <div className="flex items-center gap-2 mb-3">
        <div className="p-1 rounded-full bg-amber-100">
          <Clock className="w-4 h-4 text-amber-600" />
        </div>
        <span className="text-sm font-medium text-amber-800">等待您的确认</span>
      </div>
      
      {/* 消息 */}
      <p className="text-sm text-gray-700 mb-4">{request.message}</p>
      
      {/* 选项按钮 */}
      <div className="flex flex-wrap gap-2">
        {request.options.map((option) => (
          <button
            key={option.id}
            onClick={() => onSelect?.(option.id)}
            className={cn(
              'inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all',
              option.recommended
                ? 'bg-indigo-600 text-white hover:bg-indigo-700 shadow-sm shadow-indigo-200'
                : 'bg-white border border-gray-200 text-gray-700 hover:border-gray-300 hover:bg-gray-50'
            )}
          >
            {option.icon && <span>{option.icon}</span>}
            {option.label}
            {option.recommended && (
              <span className="inline-flex items-center gap-1 text-xs bg-white/20 px-1.5 py-0.5 rounded">
                <CheckCircle2 className="w-3 h-3" />
                推荐
              </span>
            )}
          </button>
        ))}
      </div>
      
      {/* 提示 */}
      {request.allowTextInput && (
        <p className="text-xs text-gray-500 mt-3 flex items-center gap-1">
          <span>💡</span>
          您也可以在输入框中直接输入回复
        </p>
      )}
    </div>
  );
}
```

#### components/chat/Message/SystemMessage.tsx
```typescript
// frontend/src/components/chat/Message/SystemMessage.tsx
'use client';

import { Info, AlertCircle, CheckCircle } from 'lucide-react';
import { Message } from '@/types/message';
import { cn } from '@/lib/cn';

interface SystemMessageProps {
  message: Message;
}

export function SystemMessage({ message }: SystemMessageProps) {
  // 根据内容判断类型
  const isError = message.content.includes('错误') || message.content.includes('失败');
  const isSuccess = message.content.includes('完成') || message.content.includes('成功');
  
  const Icon = isError ? AlertCircle : isSuccess ? CheckCircle : Info;
  const colors = isError
    ? 'bg-red-50 border-red-200 text-red-700'
    : isSuccess
    ? 'bg-green-50 border-green-200 text-green-700'
    : 'bg-gray-50 border-gray-200 text-gray-600';
  
  return (
    <div className="flex justify-center my-4">
      <div
        className={cn(
          'inline-flex items-center gap-2 px-4 py-2 rounded-full border text-sm',
          colors
        )}
      >
        <Icon className="w-4 h-4" />
        <span>{message.content}</span>
      </div>
    </div>
  );
}
```

#### components/chat/InputArea.tsx
```typescript
// frontend/src/components/chat/InputArea.tsx
'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Square, Paperclip, Sparkles } from 'lucide-react';
import { ConfirmationRequest } from '@/types/message';
import { cn } from '@/lib/cn';

interface InputAreaProps {
  onSend: (content: string) => void;
  onStop: () => void;
  isExecuting: boolean;
  disabled?: boolean;
  pendingConfirmation?: ConfirmationRequest | null;
  onConfirmation?: (optionId: string) => void;
}

export function InputArea({
  onSend,
  onStop,
  isExecuting,
  disabled = false,
  pendingConfirmation,
  onConfirmation,
}: InputAreaProps) {
  const [content, setContent] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  
  // 自动调整高度
  const adjustHeight = useCallback(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  }, []);
  
  useEffect(() => {
    adjustHeight();
  }, [content, adjustHeight]);
  
  // 快捷键
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isExecuting) {
        e.preventDefault();
        onStop();
      }
    };
    
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isExecuting, onStop]);
  
  const handleSubmit = () => {
    if (!content.trim() || isExecuting || disabled) return;
    onSend(content.trim());
    setContent('');
    
    // 重置高度
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };
  
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };
  
  const placeholder = isExecuting
    ? 'Agent 正在执行，请等待...'
    : pendingConfirmation
    ? '输入回复或点击上方按钮确认...'
    : '输入品牌名称开始分析，如：观夏';
  
  return (
    <div className="border-t bg-white">
      {/* 快捷确认按钮 */}
      {pendingConfirmation && !isExecuting && (
        <div className="px-4 py-2 border-b bg-gray-50">
          <div className="max-w-3xl mx-auto flex items-center gap-2">
            <span className="text-xs text-gray-500">快捷回复：</span>
            {pendingConfirmation.options.slice(0, 3).map((option) => (
              <button
                key={option.id}
                onClick={() => onConfirmation?.(option.id)}
                className={cn(
                  'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                  option.recommended
                    ? 'bg-indigo-100 text-indigo-700 hover:bg-indigo-200'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      )}
      
      {/* 输入区 */}
      <div className="px-4 py-4">
        <div className="max-w-3xl mx-auto">
          <div
            className={cn(
              'flex items-end gap-3 p-3 rounded-2xl border transition-all',
              'bg-gray-50 border-gray-200',
              'focus-within:bg-white focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-500/20',
              disabled && 'opacity-50 cursor-not-allowed'
            )}
          >
            {/* 附件按钮 */}
            <button
              className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              title="附件"
              disabled={isExecuting || disabled}
            >
              <Paperclip className="w-5 h-5" />
            </button>
            
            {/* 输入框 */}
            <textarea
              ref={textareaRef}
              value={content}
              onChange={(e) => setContent(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={placeholder}
              disabled={isExecuting || disabled}
              rows={1}
              className={cn(
                'flex-1 resize-none border-0 bg-transparent text-sm leading-6',
                'focus:outline-none focus:ring-0',
                'placeholder:text-gray-400',
                'min-h-[24px] max-h-[200px]',
                'disabled:cursor-not-allowed'
              )}
            />
            
            {/* 发送/停止按钮 */}
            {!isExecuting ? (
              <button
                onClick={handleSubmit}
                disabled={!content.trim() || disabled}
                className={cn(
                  'p-2.5 rounded-xl transition-all',
                  content.trim() && !disabled
                    ? 'bg-indigo-600 text-white hover:bg-indigo-700 shadow-sm shadow-indigo-200'
                    : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                )}
              >
                <Send className="w-5 h-5" />
              </button>
            ) : (
              <button
                onClick={onStop}
                className="p-2.5 rounded-xl bg-red-600 text-white hover:bg-red-700 shadow-sm shadow-red-200 transition-colors"
              >
                <Square className="w-5 h-5" />
              </button>
            )}
          </div>
          
          {/* 提示文字 */}
          <div className="flex items-center justify-center gap-4 mt-2 text-xs text-gray-400">
            <span className="flex items-center gap-1">
              <kbd className="px-1.5 py-0.5 bg-gray-100 rounded text-gray-500">Enter</kbd>
              发送
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-1.5 py-0.5 bg-gray-100 rounded text-gray-500">Shift + Enter</kbd>
              换行
            </span>
            {isExecuting && (
              <span className="flex items-center gap-1">
                <kbd className="px-1.5 py-0.5 bg-gray-100 rounded text-gray-500">Esc</kbd>
                停止
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
```

#### components/chat/ProgressIndicator.tsx
```typescript
// frontend/src/components/chat/ProgressIndicator.tsx
'use client';

import { Loader2 } from 'lucide-react';
import { ExecutionProgress } from '@/types/agent';
import { TPAORBlock } from './Message/TPAORBlock';
import { formatProgress, formatTimeRemaining } from '@/lib/utils';
import { cn } from '@/lib/cn';

interface CurrentTPAOR {
  thought: string;
  plan: string;
  action: string;
  observation: string;
  activePhase: 'thought' | 'plan' | 'action' | 'observation' | null;
}

interface ProgressIndicatorProps {
  tpaor: CurrentTPAOR;
  progress: ExecutionProgress | null;
  className?: string;
}

export function ProgressIndicator({ tpaor, progress, className }: ProgressIndicatorProps) {
  return (
    <div className={cn('flex gap-3', className)}>
      {/* Agent 头像 */}
      <div className="flex-shrink-0">
        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-sm">
          <Loader2 className="w-4 h-4 text-white animate-spin" />
        </div>
      </div>
      
      {/* 内容 */}
      <div className="flex-1 min-w-0 space-y-3">
        {/* TPAOR 块 */}
        {tpaor.thought && (
          <TPAORBlock
            phase="thought"
            content={tpaor.thought}
            isActive={tpaor.activePhase === 'thought'}
            defaultExpanded={tpaor.activePhase === 'thought'}
          />
        )}
        
        {tpaor.plan && (
          <TPAORBlock
            phase="plan"
            content={tpaor.plan}
            isActive={tpaor.activePhase === 'plan'}
            defaultExpanded={tpaor.activePhase === 'plan'}
          />
        )}
        
        {tpaor.action && (
          <TPAORBlock
            phase="action"
            content={tpaor.action}
            isActive={tpaor.activePhase === 'action'}
            defaultExpanded={true}
            progress={progress?.progress}
          />
        )}
        
        {/* 进度详情 */}
        {progress && (
          <div className="bg-gray-50 rounded-xl p-4 border border-gray-100">
            {/* 阶段信息 */}
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-gray-900">
                  {progress.stageName}
                </span>
                <span className="text-xs text-gray-500">
                  ({progress.stageIndex}/{progress.totalStages})
                </span>
              </div>
              <span className="text-sm font-medium text-indigo-600">
                {formatProgress(progress.progress)}
              </span>
            </div>
            
            {/* 进度条 */}
            <div className="h-2 bg-gray-200 rounded-full overflow-hidden mb-3">
              <div
                className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 rounded-full transition-all duration-500"
                style={{ width: `${progress.progress * 100}%` }}
              />
            </div>
            
            {/* 子任务 */}
            {progress.subTasks && progress.subTasks.length > 0 && (
              <div className="space-y-2">
                {progress.subTasks.map((task) => (
                  <div
                    key={task.id}
                    className="flex items-center justify-between text-sm"
                  >
                    <span className="text-gray-600 flex items-center gap-2">
                      {task.platform && (
                        <span className="px-1.5 py-0.5 bg-gray-200 rounded text-xs">
                          {task.platform}
                        </span>
                      )}
                      {task.name}
                    </span>
                    <span
                      className={cn(
                        'px-2 py-0.5 rounded-full text-xs font-medium',
                        task.status === 'completed' && 'bg-green-100 text-green-700',
                        task.status === 'running' && 'bg-amber-100 text-amber-700',
                        task.status === 'pending' && 'bg-gray-100 text-gray-500',
                        task.status === 'failed' && 'bg-red-100 text-red-700'
                      )}
                    >
                      {task.status === 'completed' && '✓ 完成'}
                      {task.status === 'running' && '● 进行中'}
                      {task.status === 'pending' && '○ 等待'}
                      {task.status === 'failed' && '✗ 失败'}
                    </span>
                  </div>
                ))}
              </div>
            )}
            
            {/* 预计剩余时间 */}
            {progress.estimatedTimeRemaining && (
              <div className="text-xs text-gray-500 mt-2 text-right">
                预计剩余 {formatTimeRemaining(progress.estimatedTimeRemaining)}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
```

#### components/chat/BrowserStateAlert.tsx
```typescript
// frontend/src/components/chat/BrowserStateAlert.tsx
'use client';

import { Globe, AlertTriangle, ExternalLink, Loader2 } from 'lucide-react';
import { BrowserState } from '@/types/agent';
import { cn } from '@/lib/cn';

interface BrowserStateAlertProps {
  state: BrowserState;
  className?: string;
}

const platformNames = {
  kimi: 'Kimi',
  deepseek: 'DeepSeek',
};

export function BrowserStateAlert({ state, className }: BrowserStateAlertProps) {
  if (!state.requiresAction) return null;
  
  return (
    <div
      className={cn(
        'rounded-xl border-2 border-amber-300 bg-gradient-to-br from-amber-50 to-orange-50 p-4',
        'animate-pulse',
        className
      )}
    >
      <div className="flex items-start gap-4">
        {/* 图标 */}
        <div className="flex-shrink-0">
          <div className="w-12 h-12 rounded-full bg-amber-100 flex items-center justify-center">
            <Globe className="w-6 h-6 text-amber-600" />
          </div>
        </div>
        
        {/* 内容 */}
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle className="w-5 h-5 text-amber-600" />
            <h4 className="font-semibold text-amber-900">需要您的操作</h4>
          </div>
          
          <p className="text-sm text-gray-700 mb-3">
            {state.message}
          </p>
          
          {state.actionHint && (
            <div className="flex items-center gap-2 text-sm text-amber-700 bg-amber-100 px-3 py-2 rounded-lg">
              <ExternalLink className="w-4 h-4" />
              <span>{state.actionHint}</span>
            </div>
          )}
          
          <div className="flex items-center gap-2 mt-3 text-xs text-gray-500">
            <Loader2 className="w-3 h-3 animate-spin" />
            <span>正在等待 {platformNames[state.platform]} 登录完成...</span>
          </div>
        </div>
      </div>
    </div>
  );
}
```

#### components/chat/StopExecutionStatus.tsx
```typescript
// frontend/src/components/chat/StopExecutionStatus.tsx
'use client';

import { AlertCircle, Play, RotateCcw, Save, CheckCircle2, Clock } from 'lucide-react';
import { StopState } from '@/types/agent';
import { cn } from '@/lib/cn';

interface StopExecutionStatusProps {
  state: StopState;
  onResume: () => void;
  onRetry: () => void;
  onSave: () => void;
  className?: string;
}

export function StopExecutionStatus({
  state,
  onResume,
  onRetry,
  onSave,
  className,
}: StopExecutionStatusProps) {
  return (
    <div
      className={cn(
        'rounded-xl border border-amber-200 bg-gradient-to-br from-amber-50 to-yellow-50 p-5',
        className
      )}
    >
      {/* 标题 */}
      <div className="flex items-center gap-3 mb-4">
        <div className="p-2 rounded-full bg-amber-100">
          <AlertCircle className="w-5 h-5 text-amber-600" />
        </div>
        <div>
          <h4 className="font-semibold text-amber-900">任务已停止</h4>
          <p className="text-xs text-gray-500">
            {state.stoppedAt.toLocaleTimeString('zh-CN')}
          </p>
        </div>
      </div>
      
      <div className="grid md:grid-cols-2 gap-4 mb-5">
        {/* 已完成 */}
        {state.completedStages.length > 0 && (
          <div className="bg-white/60 rounded-lg p-3">
            <div className="flex items-center gap-2 text-sm font-medium text-green-700 mb-2">
              <CheckCircle2 className="w-4 h-4" />
              已完成
            </div>
            <ul className="space-y-1">
              {state.completedStages.map((stage, i) => (
                <li key={i} className="text-sm text-gray-600 flex items-start gap-2">
                  <span className="text-green-500 mt-0.5">✓</span>
                  <span>{stage.name}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        
        {/* 未完成 */}
        {state.pendingStages.length > 0 && (
          <div className="bg-white/60 rounded-lg p-3">
            <div className="flex items-center gap-2 text-sm font-medium text-amber-700 mb-2">
              <Clock className="w-4 h-4" />
              未完成
            </div>
            <ul className="space-y-1">
              {state.pendingStages.map((stage, i) => (
                <li key={i} className="text-sm text-gray-600 flex items-start gap-2">
                  <span className="text-gray-400 mt-0.5">○</span>
                  <span>{stage.name}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      
      {/* 部分结果 */}
      {state.partialResults && (
        <div className="bg-white/60 rounded-lg p-3 mb-4">
          <div className="text-sm text-gray-600">
            已完成抓取：
            <span className="font-medium text-gray-900">
              {state.partialResults.fetchedCount}/{state.partialResults.totalCount}
            </span>
          </div>
          {state.partialResults.platforms && (
            <div className="flex gap-2 mt-2">
              {Object.entries(state.partialResults.platforms).map(([platform, data]) => (
                <span
                  key={platform}
                  className="px-2 py-1 bg-gray-100 rounded text-xs text-gray-600"
                >
                  {platform}: {data.completed}/{data.total}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
      
      {/* 操作按钮 */}
      <div className="flex flex-wrap gap-2">
        {state.canResume && (
          <button
            onClick={onResume}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium bg-indigo-600 text-white hover:bg-indigo-700 transition-colors shadow-sm"
          >
            <Play className="w-4 h-4" />
            继续执行
          </button>
        )}
        
        {state.canRetry && (
          <button
            onClick={onRetry}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium bg-white border border-gray-200 text-gray-700 hover:bg-gray-50 transition-colors"
          >
            <RotateCcw className="w-4 h-4" />
            重试此步
          </button>
        )}
        
        <button
          onClick={onSave}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium bg-white border border-gray-200 text-gray-700 hover:bg-gray-50 transition-colors"
        >
          <Save className="w-4 h-4" />
          保存进度
        </button>
      </div>
    </div>
  );
}
```

#### components/chat/MessageActions.tsx
```typescript
// frontend/src/components/chat/MessageActions.tsx
'use client';

import { useState } from 'react';
import { MoreHorizontal, Copy, Edit3, RotateCcw, Trash2, Check } from 'lucide-react';
import { Message } from '@/types/message';
import { cn } from '@/lib/cn';

interface MessageActionsProps {
  message: Message;
  className?: string;
}

export function MessageActions({ message, className }: MessageActionsProps) {
  const [showMenu, setShowMenu] = useState(false);
  const [copied, setCopied] = useState(false);
  
  const handleCopy = async () => {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  
  const handleEdit = () => {
    // TODO: 实现编辑功能
    setShowMenu(false);
  };
  
  const handleRollback = () => {
    // TODO: 实现回退功能
    setShowMenu(false);
  };
  
  const handleDelete = () => {
    // TODO: 实现删除功能
    setShowMenu(false);
  };
  
  return (
    <div className={cn('opacity-0 group-hover:opacity-100 transition-opacity', className)}>
      <div className="relative">
        <button
          onClick={() => setShowMenu(!showMenu)}
          className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
        >
          <MoreHorizontal className="w-4 h-4" />
        </button>
        
        {showMenu && (
          <>
            <div
              className="fixed inset-0 z-10"
              onClick={() => setShowMenu(false)}
            />
            <div className="absolute top-full mt-1 right-0 w-40 bg-white rounded-xl shadow-lg border py-1 z-20">
              <button
                onClick={handleCopy}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
              >
                {copied ? (
                  <Check className="w-4 h-4 text-green-500" />
                ) : (
                  <Copy className="w-4 h-4" />
                )}
                {copied ? '已复制' : '复制内容'}
              </button>
              
              {message.metadata.canEdit && (
                <button
                  onClick={handleEdit}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
                >
                  <Edit3 className="w-4 h-4" />
                  编辑重发
                </button>
              )}
              
              {message.metadata.canRollback && (
                <button
                  onClick={handleRollback}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
                >
                  <RotateCcw className="w-4 h-4" />
                  从此重发
                </button>
              )}
              
              <div className="border-t my-1" />
              
              <button
                onClick={handleDelete}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-600 hover:bg-red-50"
              >
                <Trash2 className="w-4 h-4" />
                删除消息
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
```

#### components/chat/index.ts
```typescript
// frontend/src/components/chat/index.ts
export { ChatPanel } from './ChatPanel';
export { MessageList } from './MessageList';
export { InputArea } from './InputArea';
export { ProgressIndicator } from './ProgressIndicator';
export { BrowserStateAlert } from './BrowserStateAlert';
export { StopExecutionStatus } from './StopExecutionStatus';
export { MessageActions } from './MessageActions';
```

### 5. 更新页面

#### app/chat/[sessionId]/page.tsx
```typescript
// frontend/src/app/chat/[sessionId]/page.tsx
'use client';

import { useParams } from 'next/navigation';
import { AppLayout } from '@/components/layout/AppLayout';
import { ChatPanel } from '@/components/chat';
import { CanvasPanel } from '@/components/canvas/CanvasPanel';

export default function ChatPage() {
  const params = useParams();
  const sessionId = params.sessionId as string;
  
  return (
    <AppLayout canvas={<CanvasPanel />}>
      <ChatPanel sessionId={sessionId} />
    </AppLayout>
  );
}
```

## 执行步骤

1. 创建目录结构
2. 按顺序创建所有文件
3. 安装缺失依赖（如 clsx, tailwind-merge）
4. 重启开发服务器
```bash
# 安装依赖
cd frontend
npm install clsx tailwind-merge

# 创建目录
mkdir -p src/components/chat/Message
mkdir -p src/types
mkdir -p src/lib
mkdir -p src/stores

# 重启
npm run dev
```

## 预期效果

1. 空状态显示欢迎页面和品牌快捷按钮
2. 发送消息后显示用户气泡
3. Agent 执行时显示 TPAOR 状态块（可折叠）
4. 执行进度显示进度条和子任务
5. 产出卡片可点击打开 Canvas
6. 确认请求显示选项按钮
7. 输入区支持快捷键和快捷回复