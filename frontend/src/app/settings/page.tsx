'use client';

import * as Dialog from '@radix-ui/react-dialog';
import { Suspense, useEffect, useMemo, useState, type ChangeEvent, type ReactNode } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import {
  RiArrowLeftLine,
  RiArrowDownSLine,
  RiCheckLine,
  RiCloseLine,
  RiNotification3Line,
  RiTeamLine,
} from '@remixicon/react';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { DashboardTopBar } from '@/components/layout/DashboardTopBar';
import { Button } from '@/components/ui/button';
import { modalScrimClassName } from '@/components/ui/modal-scrim';
import { ThemeToggle } from '@/components/ui/ThemeToggle';
import { toast } from '@/components/ui/toast';
import { getPlatformDisplayName } from '@/config/platformLabel';
import {
  cleanEntityDisplayText,
  primaryBrandEntities,
} from '@/lib/brandEntityHygiene';
import { cn, formatDateTime } from '@/lib/utils';
import { api } from '@/services/api';
import { useDashboardStore } from '@/stores/dashboardStore';
import { useEntityStore } from '@/stores/entityStore';
import { useMonitoringStore } from '@/stores/monitoringStore';
import type { AuthUser } from '@/types/auth';
import type { PanoramaAnalysisStatus } from '@/types/monitoring';
import {
  FREQUENCY_LABELS,
  type CreateScheduleInput,
  type MonitoringSchedule,
  type ScheduleFrequency,
  type UpdateScheduleInput,
} from '@/types/monitoring';

const SETTINGS_STORAGE_KEY = 'specta-settings-v1';
const DEFAULT_MONITORING_PLATFORMS = ['doubao', 'yuanbao', 'kimi', 'deepseek'] as const;
const FREQUENCY_OPTIONS: ScheduleFrequency[] = ['daily', 'weekly', 'biweekly', 'monthly'];
const HOUR_OPTIONS = Array.from({ length: 24 }, (_, index) => index);
const PLATFORM_OPTIONS = [
  { key: 'doubao', label: '豆包', description: '使用豆包 API 自动抓取', disabled: false },
  { key: 'yuanbao', label: '元宝', description: '使用元宝 API 自动抓取', disabled: false },
  { key: 'kimi', label: 'Kimi', description: '使用 Kimi API 自动抓取', disabled: false },
  { key: 'deepseek', label: 'DeepSeek', description: '使用 DeepSeek 网页版自动抓取', disabled: false },
] as const;

interface LocalSettings {
  defaultEntityId: string | null;
}

interface MonitoringFormState {
  frequency: ScheduleFrequency;
  preferredHour: number;
  timezone: string;
  platforms: string[];
}

type LegalDocumentId = 'terms' | 'privacy';

interface LegalPolicySection {
  title: string;
  body: string[];
  bullets?: string[];
}

interface LegalPolicyDocument {
  id: LegalDocumentId;
  title: string;
  updatedAt: string;
  intro: string;
  sections: LegalPolicySection[];
}

const DEFAULT_LOCAL_SETTINGS: LocalSettings = {
  defaultEntityId: null,
};

const LEGAL_POLICY_DOCUMENTS: Record<LegalDocumentId, LegalPolicyDocument> = {
  terms: {
    id: 'terms',
    title: 'Specta AI 用户协议',
    updatedAt: '2026年5月7日',
    intro:
      '本协议说明您访问和使用 Specta AI 时的基本规则。Specta AI 面向品牌、市场、增长和运营团队，提供品牌在 AI 答案中的表现分析、问题模拟、AI 回答抓取、来源证据整理、报告生成和自动监测等能力。',
    sections: [
      {
        title: '1. 接受本协议',
        body: [
          '当您注册、登录、访问或使用 Specta AI，即表示您已阅读并同意本协议以及平台展示的其他适用规则。',
          '如果您代表公司、团队或其他组织使用 Specta AI，您确认自己有权代表该组织接受本协议。该组织需要对其成员在工作区内的使用行为负责。',
        ],
      },
      {
        title: '2. 账户与工作区',
        body: [
          '您需要使用真实、可联系的邮箱或手机号完成登录、申请体验或工作区加入流程。请妥善保管账号凭证，不要与无关人员共享访问权限。',
          '工作区内可能包含品牌资料、问题集、AI 回答、来源链接、分析报告、自动监测计划和团队配置。管理员或被授权成员可能查看、管理或导出这些内容。',
        ],
      },
      {
        title: '3. 服务内容',
        body: [
          'Specta AI 会基于您提供或选择的品牌、官网、问题集、分析视图和监测配置，调用模型、抓取公开 AI 平台回答、提取引用来源，并生成可视化分析与报告。',
          '部分能力依赖第三方模型、公开网站、浏览器自动化、API、搜索结果或外部平台页面结构。这些外部服务可能发生限流、失败、登录要求、页面变化、数据缺失或结果不稳定。',
        ],
        bullets: [
          '品牌资料与竞品识别用于建立分析上下文。',
          '问题模拟用于生成用户可能向 AI 提问的样本。',
          'AI 答案抓取用于观察不同 AI 来源中的品牌表现。',
          '分析报告、来源证据和自动监测用于辅助判断趋势与优化动作。',
        ],
      },
      {
        title: '4. 用户内容与授权',
        body: [
          '您保留对自己提交内容的权利。为提供服务，您授权 Specta AI 在必要范围内处理、存储、转换、展示、分析和生成与该内容相关的结果。',
          '您需要确保提交的品牌资料、文件、链接、问题和其他内容不侵犯他人权利，不包含违法、恶意、误导性或未经授权披露的敏感信息。',
        ],
      },
      {
        title: '5. AI 输出与专业判断',
        body: [
          'Specta AI 使用大模型和自动化流程辅助分析。模型输出、抓取结果、来源识别、情绪判断、排名推断和建议可能存在遗漏、偏差或错误。',
          '平台输出不能作为唯一事实来源，也不能替代法律、财务、医疗、合规、公关危机处置或其他专业意见。您应结合原始来源、业务背景和人工复核后再作决策。',
        ],
      },
      {
        title: '6. 可接受使用',
        body: [
          '您不得使用 Specta AI 从事违法、侵权、欺诈、滥用、攻击系统、规避权限、批量骚扰、恶意抓取、泄露他人隐私或破坏第三方平台正常运行的行为。',
          '您也不得试图绕过平台的访问控制、计费限制、监测限制、安全检查或人工接管流程。',
        ],
      },
      {
        title: '7. 费用、试用与服务调整',
        body: [
          '如果您通过试用、邀请、订单或单独协议使用 Specta AI，具体功能范围、服务额度、价格和期限以相应页面或协议为准。',
          '我们可能根据产品演进、成本、外部平台限制或安全要求调整功能、模型、平台支持范围和服务策略。重大变化会通过产品界面或合理方式提示。',
        ],
      },
      {
        title: '8. 暂停与终止',
        body: [
          '如发现账号存在安全风险、违反本协议、损害其他用户或第三方权益、影响平台稳定性，或法律法规要求我们采取行动，我们可能暂停或终止相关账号、工作区或功能访问。',
          '您可以停止使用平台，并可通过平台提供的方式或联系我们申请处理账户和数据。',
        ],
      },
      {
        title: '9. 知识产权',
        body: [
          'Specta AI 的产品界面、系统设计、代码、商标、服务名称、模型编排、分析结构和文档由我们或相关权利人所有。',
          '除非另有约定，您不得复制、反向工程、出售、转授权或以混淆来源的方式使用 Specta AI 的品牌和服务资产。',
        ],
      },
      {
        title: '10. 免责声明与责任限制',
        body: [
          '在法律允许范围内，Specta AI 按现有状态提供。我们会努力保障服务稳定和结果质量，但不承诺服务永不中断、完全准确、完全满足您的所有业务目标，或外部平台始终可用。',
          '因您使用、依赖或分享平台输出而产生的商业决策、声誉影响、数据处理、第三方争议或其他间接损失，应由您结合自身判断承担相应风险。',
        ],
      },
      {
        title: '11. 协议更新与联系我们',
        body: [
          '我们可能不时更新本协议。更新后会在设置页或其他合理位置展示新的生效版本。',
          '如果您对本协议或平台使用规则有疑问，可通过 Specta AI 官方支持渠道联系我们。',
        ],
      },
    ],
  },
  privacy: {
    id: 'privacy',
    title: 'Specta AI 隐私条款',
    updatedAt: '2026年5月7日',
    intro:
      '本隐私条款说明 Specta AI 在提供品牌 AI 答案分析、报告生成、来源证据整理和自动监测服务时，如何收集、使用、保存和保护与您或您的工作区相关的信息。',
    sections: [
      {
        title: '1. 我们收集的信息',
        body: [
          '我们会根据您使用的功能收集不同类型的信息。某些信息由您主动提供，某些信息来自您使用服务时产生的记录，某些信息来自公开网页、AI 平台回答或第三方服务返回结果。',
        ],
        bullets: [
          '账户信息：邮箱、手机号、登录状态、组织或团队信息、角色和申请体验资料。',
          '品牌与工作区内容：品牌名称、官网、竞品、行业背景、问题集、分析视图、自动监测配置和成员操作记录。',
          '用户输入与上传内容：您在 Chat、Dashboard、设置或工具中输入的问题、文件、链接、备注和确认选择。',
          'AI 抓取与分析结果：不同 AI 来源的回答、引用链接、来源域名、截图或失败证据、报告、指标、Artifacts 和版本记录。',
          '使用与日志数据：设备和浏览器信息、IP 地址、访问时间、接口请求、错误日志、模型调用观测、token 使用、缓存命中和安全审计记录。',
        ],
      },
      {
        title: '2. 我们如何使用信息',
        body: [
          '我们使用上述信息是为了提供、维护、保护和改进 Specta AI，并帮助您理解品牌在 AI 答案中的表现。',
        ],
        bullets: [
          '创建和维护账号、工作区、品牌档案和默认设置。',
          '生成用户画像、问题模拟、AI 答案抓取、来源识别、指标计算和分析报告。',
          '执行周期监测、失败重试、人工接管、异常诊断和任务状态通知。',
          '提供客户支持、排查问题、统计系统成本、提升提示词复用和服务稳定性。',
          '防范欺诈、滥用、未授权访问、系统攻击和违反平台规则的行为。',
        ],
      },
      {
        title: '3. 第三方模型、平台与服务提供商',
        body: [
          '为完成分析任务，Specta AI 可能会把必要的品牌上下文、问题、链接或任务指令发送给第三方模型、AI 平台、浏览器自动化环境、云服务、邮件服务或日志监控服务。',
          '我们会尽量只发送完成任务所需的信息，但第三方服务对数据的处理也可能受其自身条款、隐私政策、技术限制和风控策略影响。',
        ],
        bullets: [
          '模型和 AI 平台可能包括 DeepSeek、Kimi、豆包、元宝、GLM 或后续接入的同类服务。',
          '浏览器自动化可能访问公开网页或 AI 平台页面，用于获取回答、引用和失败证据。',
          '基础设施服务可能用于托管、数据库、对象存储、邮件、日志、安全和部署。',
        ],
      },
      {
        title: '4. 数据留存',
        body: [
          '我们会在提供服务、满足安全审计、排查问题、履行法律义务或维护合法权益所需的期限内保留数据。',
          '品牌档案、问题集、报告、Artifacts、监测计划和历史记录通常会保留到您或管理员删除、关闭工作区，或我们根据协议终止相关服务为止。错误日志、模型观测和安全审计记录可能按运维需要保留一段时间。',
        ],
      },
      {
        title: '5. 数据控制',
        body: [
          '您可以在产品中管理默认品牌、自动监测计划、监测平台、问题集和部分报告内容。具备权限的管理员可以管理工作区和成员访问。',
          '如需访问、更正、导出或删除与账号或工作区相关的数据，可通过平台支持渠道联系我们。我们会根据您的身份、权限、法律义务和技术可行性处理请求。',
        ],
      },
      {
        title: '6. 我们是否用客户内容训练模型',
        body: [
          '除非另有明确说明或取得授权，Specta AI 不会主动将客户工作区中的私有内容用于训练公开通用模型。',
          '但当任务需要调用第三方模型或外部 AI 平台时，相关输入和输出可能会被这些服务按其自身规则处理。请避免提交不应进入第三方处理链路的敏感信息。',
        ],
      },
      {
        title: '7. 信息披露',
        body: [
          '我们不会出售您的个人信息。我们仅在提供服务、获得授权、履行法律义务、保护平台安全或处理企业交易等必要情况下共享信息。',
        ],
        bullets: [
          '与供应商共享：托管、数据库、邮件、模型、浏览器自动化、安全、日志和客户支持服务商。',
          '与工作区成员共享：同一工作区内有权限的成员可能看到品牌资料、任务记录、报告和监测配置。',
          '依法披露：在法律法规、监管要求、司法程序或保护用户和平台安全所必要时披露。',
        ],
      },
      {
        title: '8. 安全',
        body: [
          '我们会采用合理的技术和管理措施保护数据，例如访问控制、权限校验、日志审计、加密传输、环境隔离和安全监测。',
          '任何互联网服务都无法保证绝对安全。请谨慎提交高度敏感、受监管或未经授权的数据，并及时管理账号访问权限。',
        ],
      },
      {
        title: '9. 儿童与未成年人',
        body: [
          'Specta AI 面向企业和专业团队，不面向儿童或未成年人提供服务。未成年人不应在未获得监护人和所在组织授权的情况下使用本平台。',
        ],
      },
      {
        title: '10. 准确性说明',
        body: [
          '大模型生成内容和自动抓取结果可能不完整或不准确。涉及个人、品牌、竞品、风险事件、来源证据或市场判断的信息，应结合原始来源和人工复核后使用。',
        ],
      },
      {
        title: '11. 条款更新与联系我们',
        body: [
          '我们可能根据产品功能、法律要求或数据处理方式变化更新本隐私条款。更新后会在设置页或其他合理位置展示新的版本。',
          '如您对隐私、数据使用或账号数据请求有疑问，可通过 Specta AI 官方支持渠道联系我们。',
        ],
      },
    ],
  },
};

function getDefaultTimezone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Hong_Kong';
}

function readLocalSettings(): LocalSettings {
  if (typeof window === 'undefined') return DEFAULT_LOCAL_SETTINGS;
  try {
    const raw = window.localStorage.getItem(SETTINGS_STORAGE_KEY);
    if (!raw) return DEFAULT_LOCAL_SETTINGS;
    return {
      ...DEFAULT_LOCAL_SETTINGS,
      ...(JSON.parse(raw) as Partial<LocalSettings>),
    };
  } catch {
    return DEFAULT_LOCAL_SETTINGS;
  }
}

function saveLocalSettings(settings: LocalSettings) {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
  }
}

function filterSupportedMonitoringPlatforms(platforms: string[] | null | undefined): string[] {
  return (platforms || []).filter(
    (platform): platform is string =>
      PLATFORM_OPTIONS.some((option) => option.key === platform && !option.disabled)
  );
}

function createMonitoringForm(schedule: MonitoringSchedule | null, timezone: string): MonitoringFormState {
  const platforms = schedule
    ? filterSupportedMonitoringPlatforms(schedule.platforms)
    : [...DEFAULT_MONITORING_PLATFORMS];

  return {
    frequency: schedule?.frequency || 'weekly',
    preferredHour: schedule?.preferred_hour ?? 9,
    timezone: schedule?.timezone || timezone,
    platforms,
  };
}

function monitorMetricLabel(metric?: string | null) {
  if (metric === 'mention_rate') return 'AI 提及率';
  if (metric === 'mention_ranking') return '提及排名';
  if (metric === 'official_citation_rate') return '官网引用率';
  if (metric === 'sentiment_distribution') return '语气性质';
  return '品牌情报指标';
}

function getStatusLabel(status: MonitoringSchedule['status'] | 'inactive') {
  switch (status) {
    case 'active':
      return '运行中';
    case 'paused':
      return '已暂停';
    case 'error':
      return '异常';
    case 'completed':
      return '已完成';
    default:
      return '未启用';
  }
}

function getStatusTone(status: MonitoringSchedule['status'] | 'inactive') {
  if (status === 'active') {
    return { border: 'rgba(34,197,94,0.34)', bg: 'rgba(34,197,94,0.12)', text: 'var(--success)' };
  }
  if (status === 'paused') {
    return { border: 'rgba(245,158,11,0.34)', bg: 'rgba(245,158,11,0.12)', text: 'var(--warning)' };
  }
  if (status === 'error') {
    return { border: 'rgba(239,68,68,0.34)', bg: 'rgba(239,68,68,0.12)', text: 'var(--error)' };
  }
  return { border: 'var(--border-subtle)', bg: 'var(--bg-tertiary)', text: 'var(--text-secondary)' };
}

function formatAccountStatusLabel(status?: string | null) {
  switch (status) {
    case 'active':
      return '正常';
    case 'pending_review':
      return '待开通';
    case 'suspended':
      return '已停用';
    default:
      return '--';
  }
}

function formatHour(hour: number) {
  return `${String(hour).padStart(2, '0')}:00`;
}

function formatPercent(value: number | null | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '--';
  const normalized = value <= 1 ? value * 100 : value;
  return `${normalized.toFixed(1)}%`;
}

function SectionCard({
  id,
  eyebrow,
  title,
  description,
  tone,
  actions,
  children,
}: {
  id: string;
  eyebrow: string;
  title: string;
  description?: string;
  tone: 'analysis' | 'mint';
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      className={cn(
        'dashboard-board rounded-[28px] border px-5 py-5 md:px-7 md:py-7',
        tone === 'analysis' && 'dashboard-board--analysis',
        tone === 'mint' && 'dashboard-board--mint'
      )}
    >
      <div
        className="flex flex-col gap-4 border-b pb-5 md:flex-row md:items-end md:justify-between"
        style={{ borderColor: 'var(--border-subtle)' }}
      >
        <div className="max-w-2xl">
          <div className="text-[11px] font-semibold uppercase tracking-[0.22em]" style={{ color: 'var(--text-tertiary)' }}>
            {eyebrow}
          </div>
          <h2 className="mt-2 text-xl font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>
            {title}
          </h2>
          {description ? (
            <p className="mt-2 text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
              {description}
            </p>
          ) : null}
        </div>
        {actions}
      </div>
      <div className="mt-6">{children}</div>
    </section>
  );
}

function LegalPolicySection({
  onOpen,
}: {
  onOpen: (documentId: LegalDocumentId) => void;
}) {
  return (
    <SectionCard
      id="legal"
      tone="analysis"
      eyebrow="法律与隐私"
      title="用户协议与隐私条款"
      description="查看 Specta AI 的服务使用规则、数据处理范围和隐私保护说明。"
      actions={
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" size="md" onClick={() => onOpen('terms')}>
            用户协议
          </Button>
          <Button variant="secondary" size="md" onClick={() => onOpen('privacy')}>
            隐私条款
          </Button>
        </div>
      }
    >
      <div className="grid gap-4 md:grid-cols-2">
        {(['terms', 'privacy'] as LegalDocumentId[]).map((documentId) => {
          const policy = LEGAL_POLICY_DOCUMENTS[documentId];
          return (
            <button
              key={policy.id}
              type="button"
              onClick={() => onOpen(policy.id)}
              className="rounded-xl border px-5 py-5 text-left transition-transform hover:-translate-y-0.5"
              style={{
                borderColor: 'var(--border-subtle)',
                backgroundColor: 'var(--bg-tertiary)',
              }}
            >
              <div className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
                {policy.title}
              </div>
              <div className="mt-1 text-xs" style={{ color: 'var(--text-tertiary)' }}>
                更新日期：{policy.updatedAt}
              </div>
              <p className="mt-3 line-clamp-3 text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
                {policy.intro}
              </p>
              <div className="mt-4 text-sm font-medium" style={{ color: 'var(--brand-primary)' }}>
                查看完整内容
              </div>
            </button>
          );
        })}
      </div>
    </SectionCard>
  );
}

function LegalPolicyDialog({
  policy,
  onClose,
}: {
  policy: LegalPolicyDocument | null;
  onClose: () => void;
}) {
  if (!policy) return null;

  return (
    <Dialog.Root open={Boolean(policy)} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className={modalScrimClassName('z-50')} />
        <Dialog.Content className="fixed inset-0 z-50 flex items-center justify-center p-4 md:p-6">
          <div className="flex h-[min(92vh,980px)] w-[min(96vw,1080px)] flex-col overflow-hidden rounded-[28px] border bg-[var(--bg-elevated)] shadow-2xl" style={{ borderColor: 'var(--border-subtle)' }}>
            <div className="flex items-start justify-between gap-4 border-b px-5 py-5 md:px-7" style={{ borderColor: 'var(--border-subtle)' }}>
              <div>
                <Dialog.Title className="text-[24px] font-semibold tracking-tight text-[var(--text-primary)]">
                  {policy.title}
                </Dialog.Title>
                <Dialog.Description className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                  更新日期：{policy.updatedAt}
                </Dialog.Description>
              </div>
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full border transition-colors hover:bg-[var(--bg-tertiary)]"
                  style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-secondary)' }}
                  aria-label="关闭法律条款"
                >
                  <RiCloseLine className="h-5 w-5" />
                </button>
              </Dialog.Close>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 md:px-7 md:py-6">
              <div className="grid gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
                <aside className="h-fit rounded-xl border px-4 py-4 lg:sticky lg:top-0" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                  <div className="text-xs font-semibold uppercase tracking-[0.18em]" style={{ color: 'var(--text-tertiary)' }}>
                    目录
                  </div>
                  <ol className="mt-3 space-y-2 text-sm leading-5" style={{ color: 'var(--text-secondary)' }}>
                    {policy.sections.map((section) => (
                      <li key={section.title}>{section.title.replace(/^\d+\.\s*/, '')}</li>
                    ))}
                  </ol>
                </aside>

                <article className="min-w-0">
                  <p className="rounded-xl border px-4 py-4 text-sm leading-7" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-secondary)' }}>
                    {policy.intro}
                  </p>
                  <div className="mt-6 space-y-7">
                    {policy.sections.map((section) => (
                      <section key={section.title}>
                        <h3 className="text-lg font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>
                          {section.title}
                        </h3>
                        <div className="mt-3 space-y-3 text-sm leading-7" style={{ color: 'var(--text-secondary)' }}>
                          {section.body.map((paragraph) => (
                            <p key={paragraph}>{paragraph}</p>
                          ))}
                          {section.bullets ? (
                            <ul className="list-disc space-y-2 pl-5">
                              {section.bullets.map((item) => (
                                <li key={item}>{item}</li>
                              ))}
                            </ul>
                          ) : null}
                        </div>
                      </section>
                    ))}
                  </div>
                </article>
              </div>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function FieldLabel({ label, hint }: { label: string; hint?: string }) {
  return (
    <div className="mb-2">
      <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
        {label}
      </div>
      {hint ? (
        <div className="mt-1 text-xs leading-5" style={{ color: 'var(--text-tertiary)' }}>
          {hint}
        </div>
      ) : null}
    </div>
  );
}

function NativeSelect({
  value,
  onChange,
  children,
}: {
  value: string | number;
  onChange: (event: ChangeEvent<HTMLSelectElement>) => void;
  children: ReactNode;
}) {
  return (
      <div className="relative overflow-hidden rounded-xl">
      <select
        value={value}
        onChange={onChange}
        className="h-11 w-full appearance-none rounded-xl border bg-transparent px-3 pr-12 text-sm outline-none"
        style={{
          backgroundColor: 'var(--bg-tertiary)',
          borderColor: 'var(--border-subtle)',
          color: 'var(--text-primary)',
        }}
      >
        {children}
      </select>
      <span
        className="pointer-events-none absolute inset-y-0 right-0 flex w-11 items-center justify-center border-l"
        style={{
          color: 'var(--text-secondary)',
          borderColor: 'var(--border-subtle)',
          backgroundColor: 'var(--bg-tertiary)',
        }}
      >
        <RiArrowDownSLine className="h-4 w-4" />
      </span>
    </div>
  );
}

function PillOption({
  active,
  disabled = false,
  label,
  description,
  onClick,
}: {
  active: boolean;
  disabled?: boolean;
  label: string;
  description: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={() => {
        if (!disabled) onClick();
      }}
      disabled={disabled}
      className={cn(
        'rounded-xl border px-4 py-4 text-left transition-transform',
        !disabled && 'hover:-translate-y-0.5',
        disabled && 'cursor-not-allowed opacity-70'
      )}
      style={{
        borderColor: active
          ? 'color-mix(in srgb, var(--brand-primary) 44%, var(--border-subtle) 56%)'
          : 'var(--border-subtle)',
        background: disabled
          ? 'var(--bg-tertiary)'
          : active
            ? 'color-mix(in srgb, var(--brand-primary) 10%, var(--bg-elevated) 90%)'
            : 'var(--bg-tertiary)',
      }}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          {label}
        </span>
        {disabled ? (
          <span className="text-[11px] font-medium" style={{ color: 'var(--text-tertiary)' }}>
            不可用
          </span>
        ) : active ? (
          <RiCheckLine className="h-4 w-4" style={{ color: 'var(--brand-primary)' }} />
        ) : null}
      </div>
      <div className="mt-2 text-xs leading-5" style={{ color: 'var(--text-secondary)' }}>
        {description}
      </div>
    </button>
  );
}

function PanoramaStatusBlock({
  status,
  loading,
}: {
  status: PanoramaAnalysisStatus | null;
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="rounded-xl border px-4 py-4 text-sm" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-elevated)', color: 'var(--text-secondary)' }}>
        正在读取最近一次全景分析。
      </div>
    );
  }

  if (!status?.has_report) {
    return (
      <div className="rounded-xl border px-4 py-4 text-sm leading-6" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-elevated)', color: 'var(--text-secondary)' }}>
        未建立
      </div>
    );
  }

  return (
    <div className="rounded-xl border px-4 py-4" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-elevated)' }}>
      <div className="space-y-3">
        <div>
          <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>提及率</div>
          <div className="mt-1 text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
            {formatPercent(status.mention_rate)}
          </div>
        </div>
        <div>
          <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>品牌排名</div>
          <div className="mt-1 text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
            {status.brand_rank_label || '--'}
          </div>
        </div>
        {status.created_at ? (
          <div className="text-xs leading-5" style={{ color: 'var(--text-tertiary)' }}>
            最近更新：{formatDateTime(status.created_at)}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function SettingsPageContent() {
  const searchParams = useSearchParams();
  const timezone = getDefaultTimezone();
  const requestedEntityId = searchParams.get('entity_id');
  const requestedSection = searchParams.get('section');
  const requestedMonitorMetric = searchParams.get('monitor_metric');
  const requestedContentFormat = searchParams.get('content_format');

  const { entities, isLoading: isEntityLoading, hasFetched, fetchEntities } = useEntityStore();
  const { selectedBrandId, setSelectedBrandId } = useDashboardStore();
  const { schedule, fetchSchedule, pauseSchedule, resumeSchedule } = useMonitoringStore();
  const visibleEntities = useMemo(() => primaryBrandEntities(entities), [entities]);

  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [workspaceEntityId, setWorkspaceEntityId] = useState('');
  const [monitoringEntityId, setMonitoringEntityId] = useState('');
  const [localSettings, setLocalSettings] = useState<LocalSettings>(() => readLocalSettings());
  const [monitoringForm, setMonitoringForm] = useState<MonitoringFormState>(() => createMonitoringForm(null, timezone));
  const [panoramaStatus, setPanoramaStatus] = useState<PanoramaAnalysisStatus | null>(null);
  const [isPanoramaStatusLoading, setIsPanoramaStatusLoading] = useState(false);
  const [isSavingWorkspace, setIsSavingWorkspace] = useState(false);
  const [isSavingMonitoring, setIsSavingMonitoring] = useState(false);
  const [isTogglingMonitoring, setIsTogglingMonitoring] = useState(false);
  const [activeLegalDocumentId, setActiveLegalDocumentId] = useState<LegalDocumentId | null>(null);

  useEffect(() => {
    if (!hasFetched) {
      void fetchEntities();
    }
  }, [fetchEntities, hasFetched]);

  useEffect(() => {
    let cancelled = false;
    api
      .getMe()
      .then((user) => {
        if (!cancelled) {
          setCurrentUser(user);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCurrentUser(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (visibleEntities.length === 0) return;
    const validIds = new Set(visibleEntities.map((entity) => entity.id));
    const preferredEntityId =
      [requestedEntityId, localSettings.defaultEntityId, selectedBrandId, visibleEntities[0]?.id].find(
        (value) => value && validIds.has(value)
      ) || visibleEntities[0].id;

    if (!workspaceEntityId || !validIds.has(workspaceEntityId)) {
      setWorkspaceEntityId(preferredEntityId);
    }
    if (!monitoringEntityId || !validIds.has(monitoringEntityId)) {
      setMonitoringEntityId(preferredEntityId);
    }
  }, [
    localSettings.defaultEntityId,
    monitoringEntityId,
    requestedEntityId,
    selectedBrandId,
    visibleEntities,
    workspaceEntityId,
  ]);

  useEffect(() => {
    if (!monitoringEntityId) return;
    void fetchSchedule(monitoringEntityId);
  }, [fetchSchedule, monitoringEntityId]);

  useEffect(() => {
    let cancelled = false;
    if (!monitoringEntityId) {
      setPanoramaStatus(null);
      return;
    }
    setIsPanoramaStatusLoading(true);
    api
      .getPanoramaAnalysisStatus(monitoringEntityId)
      .then((status) => {
        if (!cancelled) {
          setPanoramaStatus(status);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setPanoramaStatus(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsPanoramaStatusLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [monitoringEntityId]);

  useEffect(() => {
    setMonitoringForm(createMonitoringForm(schedule, timezone));
  }, [schedule, timezone]);

  useEffect(() => {
    if (requestedSection !== 'monitoring') return;
    const timer = window.setTimeout(() => {
      document.getElementById('monitoring')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 120);
    return () => window.clearTimeout(timer);
  }, [requestedSection, visibleEntities.length]);

  const workspaceEntity = useMemo(
    () => visibleEntities.find((entity) => entity.id === workspaceEntityId) || null,
    [visibleEntities, workspaceEntityId]
  );
  const monitoringEntity = useMemo(
    () => visibleEntities.find((entity) => entity.id === monitoringEntityId) || null,
    [visibleEntities, monitoringEntityId]
  );
  const statusTone = getStatusTone(schedule?.status || 'inactive');

  const buildMonitoringPayload = (): UpdateScheduleInput & CreateScheduleInput => ({
    entity_id: monitoringEntityId,
    frequency: monitoringForm.frequency,
    preferred_hour: monitoringForm.preferredHour,
    timezone: monitoringForm.timezone,
    platforms: filterSupportedMonitoringPlatforms(monitoringForm.platforms),
  });

  const validateMonitoringForm = () => {
    if (!monitoringEntityId) {
      toast.error('请先选择要监测的品牌');
      return false;
    }
    if (filterSupportedMonitoringPlatforms(monitoringForm.platforms).length === 0) {
      toast.error('请至少选择一个可自动抓取的平台');
      return false;
    }
    return true;
  };

  const refreshMonitoringState = async (entityId: string) => {
    await fetchSchedule(entityId);
    try {
      const latestPanorama = await api.getPanoramaAnalysisStatus(entityId);
      setPanoramaStatus(latestPanorama);
    } catch {
      setPanoramaStatus(null);
    }
  };

  const handleSaveWorkspace = async () => {
    if (!workspaceEntityId) {
      toast.error('请先选择默认品牌');
      return;
    }
    setIsSavingWorkspace(true);
    try {
      const nextSettings = { defaultEntityId: workspaceEntityId };
      saveLocalSettings(nextSettings);
      setLocalSettings(nextSettings);
      setSelectedBrandId(workspaceEntityId);
      if (!monitoringEntityId) {
        setMonitoringEntityId(workspaceEntityId);
      }
      toast.success('默认设置已保存');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '保存默认设置失败');
    } finally {
      setIsSavingWorkspace(false);
    }
  };

  const handleSaveMonitoring = async () => {
    if (!validateMonitoringForm()) return;

    setIsSavingMonitoring(true);
    try {
      const payload = buildMonitoringPayload();
      if (schedule?.id) {
        await api.updateSchedule(schedule.id, payload);
      } else {
        await api.createSchedule({
          ...payload,
          status: 'paused',
        });
      }
      await refreshMonitoringState(monitoringEntityId);
      toast.success('监测设置已保存');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '保存监测设置失败');
    } finally {
      setIsSavingMonitoring(false);
    }
  };

  const handleToggleMonitoringStatus = async () => {
    if (!validateMonitoringForm()) return;

    setIsTogglingMonitoring(true);
    try {
      const payload = buildMonitoringPayload();
      if (!schedule?.id) {
        await api.createSchedule({
          ...payload,
          status: 'active',
        });
        toast.success('已启用自动监测');
      } else if (schedule.status === 'active') {
        await pauseSchedule(schedule.id);
        toast.success('已暂停自动监测');
      } else {
        await api.updateSchedule(schedule.id, payload);
        await resumeSchedule(schedule.id);
        toast.success('已启用自动监测');
      }
      await refreshMonitoringState(monitoringEntityId);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '更新监测状态失败');
    } finally {
      setIsTogglingMonitoring(false);
    }
  };

  const handlePlatformToggle = (platform: string) => {
    const option = PLATFORM_OPTIONS.find((item) => item.key === platform);
    if (!option || option.disabled) return;
    setMonitoringForm((current) => {
      const exists = current.platforms.includes(platform);
      return {
        ...current,
        platforms: exists
          ? current.platforms.filter((item) => item !== platform)
          : [...current.platforms, platform],
      };
    });
  };

  return (
    <RequireAuth>
      <div className="min-h-screen" style={{ backgroundColor: 'var(--bg-primary)' }}>
        <DashboardTopBar />
        <div className="mx-auto flex w-full max-w-[1180px] flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8">
          <div
            className="rounded-[32px] border px-6 py-6 md:px-8"
            style={{
              borderColor: 'var(--border-subtle)',
              background:
                'linear-gradient(180deg, color-mix(in srgb, var(--bg-primary) 94%, #f3efe8 6%), color-mix(in srgb, var(--bg-elevated) 97%, #efe4d3 3%))',
            }}
          >
            <div className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
              <div className="max-w-2xl">
                <Link
                  href="/dashboard"
                  className="inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors"
                  style={{
                    borderColor: 'var(--border-subtle)',
                    color: 'var(--text-secondary)',
                    backgroundColor: 'var(--bg-elevated)',
                  }}
                >
                  <RiArrowLeftLine className="h-3.5 w-3.5" />
                  返回概览
                </Link>
                <h1 className="mt-5 text-[30px] font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>
                  设置
                </h1>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="min-w-[180px] rounded-xl border px-4 py-4" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-elevated)' }}>
                  <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>默认品牌</div>
                  <div className="mt-2 text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    {workspaceEntity?.name || '未选择'}
                  </div>
                </div>
                <div className="min-w-[180px] rounded-xl border px-4 py-4" style={{ borderColor: statusTone.border, backgroundColor: statusTone.bg }}>
                  <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>自动监测</div>
                  <div className="mt-2 text-sm font-medium" style={{ color: statusTone.text }}>
                    {getStatusLabel(schedule?.status || 'inactive')}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {isEntityLoading && visibleEntities.length === 0 ? (
            <div className="rounded-[28px] border px-6 py-8 text-sm" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-elevated)', color: 'var(--text-secondary)' }}>
              正在加载品牌列表...
            </div>
          ) : visibleEntities.length === 0 ? (
            <div className="rounded-[28px] border px-6 py-8" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-elevated)' }}>
              <div className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>还没有可设置的品牌</div>
              <div className="mt-2 text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
                请先创建品牌，再回来设置默认品牌和全景自动监测。
              </div>
              <div className="mt-5">
                <Link href="/dashboard" className="inline-flex h-10 items-center rounded-full border px-4 text-sm font-medium" style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-primary)' }}>
                  去创建品牌
                </Link>
              </div>
            </div>
          ) : (
            <>
              <SectionCard
                id="monitoring"
                tone="mint"
                eyebrow="监测设置"
                title="全景自动监测"
                actions={
                  <div className="flex flex-wrap gap-2">
                    <Button variant="secondary" size="md" onClick={() => void handleToggleMonitoringStatus()} isLoading={isTogglingMonitoring}>
                      {schedule?.status === 'active' ? '暂停监测' : '启用监测'}
                    </Button>
                    <Button variant="primary" size="md" onClick={() => void handleSaveMonitoring()} isLoading={isSavingMonitoring}>
                      保存监测设置
                    </Button>
                  </div>
                }
              >
                <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
                  <div className="space-y-6">
                    {(requestedMonitorMetric || requestedContentFormat) && (
                      <div
                        className="rounded-xl border px-4 py-3 text-sm leading-6"
                        style={{
                          borderColor: 'var(--brand-border)',
                          backgroundColor: 'var(--brand-soft)',
                          color: 'var(--text-secondary)',
                        }}
                      >
                        <div className="font-medium" style={{ color: 'var(--text-primary)' }}>
                          来自品牌情报的复查建议
                        </div>
                        <div className="mt-1">
                          {requestedMonitorMetric
                            ? `优先复查 ${monitorMetricLabel(requestedMonitorMetric)}`
                            : '优先复查品牌情报指标'}
                          {requestedContentFormat ? `，对应内容：${requestedContentFormat}` : ''}
                        </div>
                      </div>
                    )}

                    <div>
                      <FieldLabel label="监测品牌" hint="自动监测会沿用这个品牌最近一次全景分析的问题集。" />
                      <NativeSelect
                        value={monitoringEntityId}
                        onChange={(event) => setMonitoringEntityId(event.target.value)}
                      >
                        {visibleEntities.map((entity) => (
                          <option key={entity.id} value={entity.id}>
                            {cleanEntityDisplayText(entity.name, '未命名品牌')}
                          </option>
                        ))}
                      </NativeSelect>
                    </div>

                    <div>
                      <FieldLabel label="监测频率" hint="按这个频率自动抓取并更新全景分析报告。" />
                      <div className="grid gap-3 md:grid-cols-4">
                        {FREQUENCY_OPTIONS.map((frequency) => (
                          <PillOption
                            key={frequency}
                            active={monitoringForm.frequency === frequency}
                            label={FREQUENCY_LABELS[frequency]}
                            description={
                              frequency === 'daily'
                                ? '适合高频跟踪。'
                                : frequency === 'weekly'
                                  ? '适合常规回看。'
                                  : frequency === 'biweekly'
                                    ? '适合稳定品牌。'
                                    : '适合低频巡检。'
                            }
                            onClick={() => setMonitoringForm((current) => ({ ...current, frequency }))}
                          />
                        ))}
                      </div>
                    </div>

                    <div>
                      <FieldLabel label="执行时间" hint="到点后开始执行。" />
                      <NativeSelect
                        value={monitoringForm.preferredHour}
                        onChange={(event) =>
                          setMonitoringForm((current) => ({
                            ...current,
                            preferredHour: Number(event.target.value),
                          }))
                        }
                      >
                        {HOUR_OPTIONS.map((hour) => (
                          <option key={hour} value={hour}>
                            {formatHour(hour)}
                          </option>
                        ))}
                      </NativeSelect>
                    </div>

                    <div>
                      <FieldLabel label="监测平台" hint="豆包、元宝、Kimi 使用 API 自动抓取；DeepSeek 使用网页版自动抓取。" />
                      <div className="grid gap-3 md:grid-cols-2">
                        {PLATFORM_OPTIONS.map((option) => (
                          <PillOption
                            key={option.key}
                            active={monitoringForm.platforms.includes(option.key)}
                            disabled={option.disabled}
                            label={option.label}
                            description={option.description}
                            onClick={() => handlePlatformToggle(option.key)}
                          />
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="rounded-xl border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                    <div className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                      <RiNotification3Line className="h-4 w-4" />
                      当前状态
                    </div>

                    <div className="mt-4 rounded-xl border px-4 py-4" style={{ borderColor: statusTone.border, backgroundColor: statusTone.bg }}>
                      <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>状态</div>
                      <div className="mt-1 text-sm font-medium" style={{ color: statusTone.text }}>
                        {getStatusLabel(schedule?.status || 'inactive')}
                      </div>
                    </div>

                    <div className="mt-4 space-y-3 text-sm" style={{ color: 'var(--text-secondary)' }}>
                      <div className="flex justify-between gap-4">
                        <span>当前品牌</span>
                        <span style={{ color: 'var(--text-primary)' }}>{monitoringEntity?.name || '--'}</span>
                      </div>
                      <div className="flex justify-between gap-4">
                        <span>下次执行</span>
                        <span style={{ color: 'var(--text-primary)' }}>
                          {schedule?.next_run_at ? formatDateTime(schedule.next_run_at) : '--'}
                        </span>
                      </div>
                      <div className="flex justify-between gap-4">
                        <span>上次执行</span>
                        <span style={{ color: 'var(--text-primary)' }}>
                          {schedule?.last_run_at ? formatDateTime(schedule.last_run_at) : '--'}
                        </span>
                      </div>
                      <div>
                        <div className="mb-2 text-xs font-medium" style={{ color: 'var(--text-tertiary)' }}>
                          全景分析状态
                        </div>
                        <PanoramaStatusBlock status={panoramaStatus} loading={isPanoramaStatusLoading} />
                      </div>
                      <div className="flex justify-between gap-4">
                        <span>监测平台</span>
                        <span className="text-right" style={{ color: 'var(--text-primary)' }}>
                          {monitoringForm.platforms.length > 0
                            ? monitoringForm.platforms.map((platform) => getPlatformDisplayName(platform)).join('、')
                            : '--'}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </SectionCard>

              <SectionCard
                id="account"
                tone="analysis"
                eyebrow="账户与工作区"
                title="默认品牌与账号信息"
                actions={
                  <Button variant="secondary" size="md" onClick={() => void handleSaveWorkspace()} isLoading={isSavingWorkspace}>
                    保存默认设置
                  </Button>
                }
              >
                <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
                  <div className="space-y-6">
                    <div className="rounded-xl border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                      <div className="flex items-center justify-between gap-4">
                        <div>
                          <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>外观主题</div>
                          <div className="mt-1 text-xs leading-5" style={{ color: 'var(--text-secondary)' }}>
                            即时切换浅色或深色界面。
                          </div>
                        </div>
                        <ThemeToggle />
                      </div>
                    </div>

                    <div>
                      <FieldLabel label="默认品牌" hint="进入概览和对话时默认使用这个品牌。" />
                      <NativeSelect
                        value={workspaceEntityId}
                        onChange={(event) => setWorkspaceEntityId(event.target.value)}
                      >
                        {visibleEntities.map((entity) => (
                          <option key={entity.id} value={entity.id}>
                            {cleanEntityDisplayText(entity.name, '未命名品牌')}
                          </option>
                        ))}
                      </NativeSelect>
                    </div>
                  </div>

                  <div className="rounded-xl border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                    <div className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                      <RiTeamLine className="h-4 w-4" />
                      当前账号
                    </div>
                    <div className="mt-4 space-y-3 text-sm" style={{ color: 'var(--text-secondary)' }}>
                      <div className="flex justify-between gap-4">
                        <span>默认品牌</span>
                        <span style={{ color: 'var(--text-primary)' }}>{workspaceEntity?.name || '--'}</span>
                      </div>
                      <div className="flex justify-between gap-4">
                        <span>登录账号</span>
                        <span style={{ color: 'var(--text-primary)' }}>{currentUser?.email || currentUser?.phone || '--'}</span>
                      </div>
                      <div className="flex justify-between gap-4">
                        <span>账户状态</span>
                        <span style={{ color: 'var(--text-primary)' }}>{formatAccountStatusLabel(currentUser?.status)}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </SectionCard>
            </>
          )}
          <LegalPolicySection onOpen={setActiveLegalDocumentId} />
          <LegalPolicyDialog
            policy={activeLegalDocumentId ? LEGAL_POLICY_DOCUMENTS[activeLegalDocumentId] : null}
            onClose={() => setActiveLegalDocumentId(null)}
          />
        </div>
      </div>
    </RequireAuth>
  );
}

export default function SettingsPage() {
  return (
    <Suspense fallback={null}>
      <SettingsPageContent />
    </Suspense>
  );
}
