import Link from 'next/link';
import type { ReactNode } from 'react';
import {
  RiArrowRightUpLine,
  RiBarChartBoxLine,
  RiChat3Line,
  RiCompass3Line,
  RiFileChartLine,
  RiGlobalLine,
  RiRadarLine,
  RiSparklingLine,
} from '@remixicon/react';

import { PublicBrand } from '@/components/layout/PublicBrand';
import { MonitoringLogicShowcase } from '@/components/marketing/MonitoringLogicShowcase';

const trackedPlatforms = ['豆包', '元宝', 'Kimi', 'DeepSeek'];

const analysisTracks = [
  {
    badge: '01',
    title: '基线分析',
    subtitle: '全景掌控',
    description: '先看品牌在 4 个主流 AI 平台里的提及、引用和主题覆盖。',
    tone: 'amber',
  },
  {
    badge: '02',
    title: '用户画像分析',
    subtitle: '聚焦场景',
    description: '再按人群和业务主题收窄，找到更高价值的问法和场景。',
    tone: 'green',
  },
  {
    badge: '03',
    title: '引用源置信度',
    subtitle: '判断可信来源',
    description: '最后判断哪些来源更可信，哪些来源真正影响 AI 的推荐。',
    tone: 'violet',
  },
] as const;

const workflowSteps = [
  {
    step: '01',
    title: '基线分析 · 全景掌控',
    description: '先建立品牌在主流 AI 平台里的整体位置，掌握提及、引用和主题覆盖。',
  },
  {
    step: '02',
    title: '用户画像分析 · 聚焦场景',
    description: '再按画像与业务主题收窄，定位更高价值、更高意图的问答场景。',
  },
  {
    step: '03',
    title: '引用源置信度 · 判断来源',
    description: '最后确认哪些来源更可信，哪些来源真正影响 AI 的推荐结果。',
  },
];

const faqs = [
  {
    question: '基线分析会先告诉我什么？',
    answer:
      '它会先告诉你品牌在主流 AI 平台里的整体位置：提及率、引用来源分布，以及已经覆盖和仍然缺失的主题。',
  },
  {
    question: '用户画像分析解决什么问题？',
    answer:
      '它把分析从全景收窄到关键人群和业务场景，帮助你找到更高价值、更高意图的问答入口，而不是平均分散地看所有问题。',
  },
  {
    question: '引用源置信度为什么重要？',
    answer:
      '因为不是所有引用都同样有价值。你需要知道哪些来源真正影响 AI 的推荐，哪些来源更值得优先补强。',
  },
  {
    question: '为什么强调 Agent 持续推进？',
    answer:
      '因为 Specta 不是停在一张静态报告上。Agent 会在同一条对话里继续抓取、追问、判断，并把结果推进成交付物。',
  },
  {
    question: '如何获得邀请码？',
    answer:
      '先提交公司信息并验证邮箱。我们会向登记邮箱不定期发放邀请码，收到后即可进入平台。',
  },
];

const capabilityCards = [
  {
    icon: RiRadarLine,
    badge: '核心',
    badgeTone: 'amber',
    title: '基线分析 · 全景掌控',
    description:
      '把 4 个主流 AI 平台里的提及、引用和主题覆盖放进同一张基线视图，先掌握整体位置。',
    stats: [
      ['4', '平台覆盖'],
      ['基线', '整体位置'],
    ],
  },
  {
    icon: RiBarChartBoxLine,
    badge: '核心',
    badgeTone: 'green',
    title: '用户画像分析 · 聚焦场景',
    description:
      '按画像和业务主题收窄分析范围，找到更高价值、更高意图的问答场景。',
    stats: [
      ['画像', '场景聚焦'],
      ['主题', '高意图问题'],
    ],
  },
  {
    icon: RiChat3Line,
    badge: '自动化',
    badgeTone: 'violet',
    title: '引用源置信度 · 判断来源',
    description:
      '不是只看引用了谁，而是判断哪些来源更可信，哪些来源真正影响 AI 的推荐结果。',
    stats: [
      ['分层', '来源判断'],
      ['偏好', '平台差异'],
    ],
  },
  {
    icon: RiFileChartLine,
    badge: '自动化',
    badgeTone: 'rose',
    title: '对话驱动交付 · 持续推进',
    description:
      '把基线、画像、来源判断沉淀成可追问的交付物，再继续往下分析和协作。',
    stats: [
      ['追问', '继续推进'],
      ['交付', '持续更新'],
    ],
  },
] as const;

function SectionTag({ children }: { children: ReactNode }) {
  return (
    <div className="inline-flex items-center gap-2 rounded-full border border-[#e7e7e1] bg-white px-3 py-1.5 text-sm text-[#59606f]">
      {children}
    </div>
  );
}

function ProductWindow({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-[28px] border border-[#e5e5df] bg-white shadow-[0_30px_70px_rgba(17,24,39,0.08)]">
      <div className="flex items-center justify-between border-b border-[#eff1f4] px-5 py-4">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-[#f87171]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#fbbf24]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#34d399]" />
        </div>
        <div className="text-sm font-medium text-[#697181]">{title}</div>
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

function HeroPreview() {
  return (
    <ProductWindow title="对话驱动分析">
      <div className="grid gap-4 lg:grid-cols-[1.08fr_0.92fr]">
        <div className="rounded-[24px] bg-[#101828] p-5 text-white lg:row-span-2">
          <div className="flex items-center justify-between text-xs uppercase tracking-[0.18em] text-white/55">
            <span>真实回答</span>
            <span>对话快照</span>
          </div>
          <div className="mt-5 space-y-4">
            <div className="rounded-[18px] bg-white/8 px-4 py-3 text-sm leading-7 text-white/88">
              25 万预算的家用纯电 SUV 怎么选？
            </div>
            <div className="rounded-[20px] bg-white px-4 py-4 text-sm leading-7 text-[#354152]">
              AI 回答优先提到 <span className="font-semibold text-[#111827]">某汽车品牌</span>，
              在家庭场景里仍然把 <span className="font-semibold text-[#111827]">竞品品牌</span>{' '}
              放在更靠前的位置，并引用了两家汽车媒体。
            </div>
            <div className="rounded-[18px] border border-white/10 bg-white/[0.06] px-4 py-4 text-sm leading-7 text-white/84">
              Agent 已识别出 <span className="font-semibold text-white">品牌被提及</span>、<span className="font-semibold text-white">竞品压制</span> 与 <span className="font-semibold text-white">媒体引用</span>，正在继续生成品牌表现报告。
            </div>
          </div>
          <div className="mt-5 flex flex-wrap gap-2">
            {['品牌被提及', '竞品压制', '媒体引用'].map((item) => (
              <span
                key={item}
                className="rounded-full border border-white/10 bg-white/[0.06] px-3 py-1.5 text-xs text-white/70"
              >
                {item}
              </span>
            ))}
          </div>
        </div>

        <div className="rounded-[22px] bg-[#f7f8fb] px-5 py-5">
          <div className="flex items-center justify-between">
            <div className="text-xs uppercase tracking-[0.18em] text-[#8d95a4]">品牌表现报告</div>
            <div className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-[#111827]">
              已生成
            </div>
          </div>
          <div className="mt-5 grid gap-3">
            {[
              ['品牌提及率', '41.7%'],
              ['内容引用率', '100%'],
              ['主题覆盖', '10 / 12'],
            ].map(([label, value]) => (
              <div key={label} className="rounded-[18px] bg-white px-4 py-4">
                <div className="text-xs text-[#7b8494]">{label}</div>
                <div className="mt-2 text-[26px] font-semibold tracking-[-0.05em] text-[#111827]">
                  {value}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-[22px] border border-[#eceef2] bg-[#fbfbfd] px-5 py-5">
          <div className="flex items-center justify-between">
            <div className="text-xs uppercase tracking-[0.18em] text-[#8d95a4]">来源分布</div>
            <div className="text-xs text-[#94a3b8]">平台偏好</div>
          </div>
          <div className="mt-5 space-y-4">
            {[
              ['豆包', [['媒体', '48%', '#111827'], ['社区', '24%', '#4f46e5'], ['视频', '16%', '#94a3b8'], ['参数库', '12%', '#d7dce6']]],
              ['Kimi', [['媒体', '54%', '#111827'], ['社区', '20%', '#4f46e5'], ['视频', '14%', '#94a3b8'], ['参数库', '12%', '#d7dce6']]],
            ].map(([platform, segments]) => (
              <div key={platform as string}>
                <div className="mb-2 flex items-center justify-between text-sm">
                  <span className="font-semibold text-[#111827]">{platform as string}</span>
                  <span className="text-[#7b8494]">引用偏好</span>
                </div>
                <div className="flex h-9 overflow-hidden rounded-full bg-white">
                  {(segments as string[][]).map(([label, width, color]) => (
                    <div
                      key={`${platform}-${label}`}
                      className="flex items-center justify-center text-[10px] font-semibold"
                      style={{
                        width,
                        backgroundColor: color,
                        color: color === '#d7dce6' ? '#475569' : '#ffffff',
                      }}
                    >
                      {label}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </ProductWindow>
  );
}

function WhyNowShowcase() {
  return (
    <div className="grid gap-10 lg:grid-cols-[0.92fr_0.88fr] lg:gap-12">
      <div>
        <div className="max-w-[820px] text-[18px] leading-[2] text-[#5b6472]">
          Specta 不是只告诉你“有没有风险”，而是把品牌在 AI 里的真实表现拆成三层：
          全景掌控、场景聚焦，以及来源可信度判断。
        </div>

        <div className="mt-10 border-t border-[#e5e7eb] pt-8">
          <div className="text-sm font-semibold text-[#a0a7b4]">核心分析入口</div>
          <div className="mt-5 space-y-4">
            {analysisTracks.map((item) => (
              <div
                key={item.title}
                className="rounded-[24px] border border-[#eceff4] bg-white px-5 py-5 shadow-[0_14px_32px_rgba(15,23,42,0.04)]"
              >
                <div className="flex items-start gap-4">
                  <div
                    className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full border text-base font-semibold ${
                      item.tone === 'amber'
                        ? 'border-[#f0dcc4] bg-[#fbf4ea] text-[#b7791f]'
                        : item.tone === 'green'
                          ? 'border-[#dce8d8] bg-[#eff6ed] text-[#64895b]'
                          : 'border-[#e4dff2] bg-[#f4f0fb] text-[#7c68c2]'
                    }`}
                  >
                    {item.badge}
                  </div>
                  <div>
                    <div className="text-[28px] font-semibold leading-[1.2] tracking-[-0.05em] text-[#111827]">
                      {item.title}
                      <span className="ml-3 text-[20px] font-medium tracking-[-0.03em] text-[#7b8494]">
                        {item.subtitle}
                      </span>
                    </div>
                    <div className="mt-2 text-[17px] leading-8 text-[#5b6472]">
                      {item.description}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="rounded-[32px] border border-[#e7e9ef] bg-white px-6 py-6 shadow-[0_24px_60px_rgba(15,23,42,0.06)]">
        <div className="text-sm font-semibold text-[#a0a7b4]">分析链路示意</div>
        <div className="mt-6 flex flex-wrap gap-2">
          {['基线分析', '用户画像分析', '引用源置信度'].map((tab, index) => (
            <span
              key={tab}
              className={`rounded-full px-4 py-2 text-sm font-semibold ${
                index === 0
                  ? 'bg-[#111827] text-white'
                  : 'border border-[#e4e7ee] bg-[#fafaf9] text-[#5b6472]'
              }`}
            >
              {tab}
            </span>
          ))}
        </div>

        <div className="mt-6 grid gap-4 lg:grid-cols-[0.86fr_1.14fr]">
          <div className="rounded-[24px] bg-[#fbfbfd] px-5 py-5">
            <div className="text-sm font-semibold text-[#98a1af]">基线结论</div>
            <div className="mt-4 text-[30px] font-semibold leading-[1.2] tracking-[-0.05em] text-[#111827]">
              先看品牌在 AI 中有没有被看见
            </div>
            <div className="mt-4 text-[17px] leading-[1.9] text-[#5b6472]">
              把提及率、引用来源分布和主题覆盖放进同一张基线报告，先掌握整体位置。
            </div>
            <div className="mt-6 grid gap-3">
              {[
                ['品牌提及率', '41.7%'],
                ['内容引用率', '100%'],
                ['主题覆盖', '10 / 12'],
              ].map(([label, value]) => (
                <div key={label} className="rounded-[18px] bg-white px-4 py-4">
                  <div className="text-xs text-[#7b8494]">{label}</div>
                  <div className="mt-2 text-[24px] font-semibold tracking-[-0.05em] text-[#111827]">
                    {value}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="space-y-4">
            <div className="rounded-[24px] border border-[#e4e7ee] bg-white px-5 py-5">
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold text-[#98a1af]">用户画像分析</div>
                <span className="rounded-full bg-[#eef2ff] px-3 py-1 text-xs font-semibold text-[#4f46e5]">
                  场景聚焦
                </span>
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                {[
                  ['高端家庭', '纯电 SUV'],
                  ['智驾通勤', '城市使用'],
                  ['科技尝鲜', '车型对比'],
                ].map(([persona, scene]) => (
                  <div key={persona} className="rounded-[18px] bg-[#fbfbfd] px-4 py-4">
                    <div className="text-sm font-semibold text-[#111827]">{persona}</div>
                    <div className="mt-2 text-sm text-[#5b6472]">{scene}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-[24px] border border-[#e4e7ee] bg-white px-5 py-5">
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold text-[#98a1af]">引用源置信度</div>
                <span className="rounded-full bg-[#f4f0fb] px-3 py-1 text-xs font-semibold text-[#7c68c2]">
                  来源判断
                </span>
              </div>
              <div className="mt-4 space-y-3">
                {[
                  ['汽车媒体', '高', '#dcfce7', '#166534'],
                  ['垂直社区', '中', '#eef2ff', '#4f46e5'],
                  ['参数库', '高', '#fff6dd', '#a16207'],
                ].map(([source, level, bg, color]) => (
                  <div key={source} className="flex items-center justify-between rounded-[18px] bg-[#fbfbfd] px-4 py-4">
                    <div>
                      <div className="text-sm font-semibold text-[#111827]">{source}</div>
                      <div className="mt-1 text-sm text-[#7b8494]">被多个平台高频引用</div>
                    </div>
                    <span
                      className="rounded-full px-3 py-1 text-xs font-semibold"
                      style={{ backgroundColor: bg, color }}
                    >
                      置信度 {level}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function WorkflowGrid() {
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      {workflowSteps.map((step) => (
        <div
          key={step.step}
          className="rounded-[26px] border border-[#e4e7ee] bg-white px-6 py-6 shadow-[0_16px_40px_rgba(15,23,42,0.04)]"
        >
          <div className="text-sm font-semibold text-[#98a1af]">{step.step}</div>
          <div className="mt-5 text-[24px] font-semibold leading-[1.25] tracking-[-0.04em] text-[#111827]">
            {step.title}
          </div>
          <div className="mt-3 text-[16px] leading-8 text-[#5b6472]">{step.description}</div>
        </div>
      ))}
    </div>
  );
}

function AgentOrchestrationMock() {
  const nodes = [
    ['A1', '品牌档案', '建立品牌与竞品上下文'],
    ['A3', '问题列表', '输出高意图问题清单'],
    ['A4', '答案抓取', '从真实平台采集回答'],
    ['A5', '品牌表现报告', '沉淀报告并继续追问'],
  ] as const;

  return (
    <div className="rounded-[30px] border border-[#e4e7ee] bg-white px-6 py-6 shadow-[0_20px_50px_rgba(15,23,42,0.05)]">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,0.94fr)_minmax(0,1.06fr)]">
        <div className="rounded-[24px] bg-[#101828] p-5 text-white">
          <div className="flex items-center justify-between text-xs uppercase tracking-[0.18em] text-white/55">
            <span>对话编排</span>
            <span>Agent 正在推进</span>
          </div>
          <div className="mt-5 space-y-3">
            <div className="max-w-[82%] rounded-[18px] bg-white/8 px-4 py-3 text-sm leading-7 text-white/86">
              帮我看一下某汽车品牌在高端纯电 SUV 场景里，哪些问题会先推荐竞品。
            </div>
            <div className="ml-auto max-w-[88%] rounded-[18px] bg-white px-4 py-4 text-sm leading-7 text-[#344054]">
              已识别出 12 个问题，正在抓取 4 个平台的真实回答。我会继续定位负向提及、竞品压制与主题缺口。
            </div>
          </div>
          <div className="mt-5 grid gap-3 sm:grid-cols-3">
            {[
              ['当前任务', '竞品压制定位'],
              ['运行状态', 'A4 -> A5'],
              ['交付方式', '对话 + 工作台'],
            ].map(([label, value]) => (
              <div
                key={label}
                className="rounded-[18px] border border-white/10 bg-white/[0.06] px-4 py-4"
              >
                <div className="text-xs text-white/55">{label}</div>
                <div className="mt-2 text-base font-semibold text-white">{value}</div>
              </div>
            ))}
          </div>
          <div className="mt-5 flex flex-wrap gap-2">
            {['继续追问', '负向提及', '竞品压制', '主题缺口'].map((tag) => (
              <span
                key={tag}
                className="rounded-full border border-white/10 bg-white/[0.06] px-3 py-1 text-xs text-white/72"
              >
                {tag}
              </span>
            ))}
          </div>
        </div>

        <div className="rounded-[24px] border border-[#eceff4] bg-[#fbfbfd] p-5">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs uppercase tracking-[0.18em] text-[#8d95a4]">Agent 编排</div>
              <div className="mt-2 text-[22px] font-semibold tracking-[-0.04em] text-[#111827]">
                一条对话，持续推进四段分析
              </div>
            </div>
            <div className="rounded-full bg-[#eef2ff] px-3 py-1 text-xs font-semibold text-[#4f46e5]">
              实时流转
            </div>
          </div>
          <div className="relative mt-6 grid gap-4 lg:grid-cols-4">
            <div className="pointer-events-none absolute left-[12%] right-[12%] top-[34px] hidden h-px bg-[#d7dce6] lg:block" />
            {nodes.map(([code, label, detail], index) => (
              <div
                key={code}
                className="relative rounded-[20px] border border-[#eceff4] bg-white px-4 py-4"
              >
                <div className="flex items-center justify-between">
                  <div className="rounded-full bg-[#111827] px-3 py-1 text-xs font-semibold text-white">
                    {code}
                  </div>
                  <div
                    className={`h-2.5 w-2.5 rounded-full ${
                      index === nodes.length - 1 ? 'bg-[#4f46e5]' : 'bg-[#34d399]'
                    }`}
                  />
                </div>
                <div className="mt-4 text-[16px] font-semibold text-[#111827]">{label}</div>
                <div className="mt-2 text-sm leading-7 text-[#5b6472]">{detail}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function CapabilityGrid() {
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {capabilityCards.map((card) => {
        const Icon = card.icon;
        const badgeClass =
          card.badgeTone === 'amber'
            ? 'bg-[#fbf4ea] text-[#b7791f]'
            : card.badgeTone === 'green'
              ? 'bg-[#eff6ed] text-[#64895b]'
              : card.badgeTone === 'violet'
                ? 'bg-[#f4f0fb] text-[#7c68c2]'
                : 'bg-[#fff1ec] text-[#c46f57]';
        return (
          <div
            key={card.title}
            className="rounded-[28px] border border-[#e4e7ee] bg-white px-6 py-6 shadow-[0_20px_50px_rgba(15,23,42,0.04)]"
          >
            <div className="flex items-start justify-between gap-4">
              <span className="flex h-12 w-12 items-center justify-center rounded-full border border-[#eceff4] bg-[#fafaf9] text-[#111827]">
                <Icon className="h-5 w-5" />
              </span>
              <span className={`rounded-full px-3 py-1 text-xs font-semibold ${badgeClass}`}>
                {card.badge}
              </span>
            </div>
            <div className="mt-6 text-[30px] font-semibold leading-[1.18] tracking-[-0.05em] text-[#111827]">
              {card.title}
            </div>
            <div className="mt-4 text-[17px] leading-[1.9] text-[#5b6472]">
              {card.description}
            </div>
            <div className="mt-8 grid gap-4 border-t border-[#eceff4] pt-5 sm:grid-cols-2">
              {card.stats.map(([value, label]) => (
                <div key={label}>
                  <div className="text-[36px] font-semibold tracking-[-0.06em] text-[#111827]">
                    {value}
                  </div>
                  <div className="text-sm text-[#7b8494]">{label}</div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function AgentCapabilityStories() {
  const stories = [
    {
      index: '01',
      title: '对话驱动分析',
      description: '在同一条对话里发起基线分析，再继续追问场景、来源和品牌表现变化。',
      visual: (
        <div className="space-y-3 rounded-[22px] bg-[#0f172a] p-4 text-white">
          <div className="max-w-[82%] rounded-[16px] bg-white/8 px-4 py-3 text-sm leading-6 text-white/86">
            基线分析出来后，继续帮我看一下高端家庭场景里哪些来源更可信。
          </div>
          <div className="ml-auto max-w-[88%] rounded-[16px] bg-white px-4 py-3 text-sm leading-6 text-[#344054]">
            已定位到 3 类高意图场景，并整理出各平台最稳定的高置信来源。
          </div>
        </div>
      ),
    },
    {
      index: '02',
      title: '真实回答采集',
      description: '不只看 API 输出，而是看用户真正看到的回答、引用和推荐顺序。',
      visual: (
        <div className="rounded-[22px] border border-[#e6eaf0] bg-[#fbfbfd] p-4">
          <div className="grid gap-3 sm:grid-cols-2">
            {[
              ['豆包', '已采集', 'bg-[#dcfce7] text-[#166534]'],
              ['Kimi', '已采集', 'bg-[#dcfce7] text-[#166534]'],
              ['元宝', '采集中', 'bg-[#eef2ff] text-[#4f46e5]'],
              ['DeepSeek', '采集中', 'bg-[#eef2ff] text-[#4f46e5]'],
            ].map(([platform, status, cls]) => (
              <div key={platform} className="rounded-[18px] bg-white px-4 py-4">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-semibold text-[#111827]">{platform}</div>
                  <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${cls}`}>
                    {status}
                  </span>
                </div>
                <div className="mt-3 h-2 rounded-full bg-[#eef2f7]">
                  <div
                    className="h-2 rounded-full bg-[#111827]"
                    style={{ width: status === '已采集' ? '100%' : '58%' }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      ),
    },
  ] as const;

  return (
    <div className="rounded-[30px] border border-[#e4e7ee] bg-white shadow-[0_20px_50px_rgba(15,23,42,0.04)]">
      {stories.map((story, index) => (
        <div
          key={story.index}
          className={`grid gap-6 px-6 py-6 lg:grid-cols-[260px_minmax(0,1fr)] lg:gap-8 ${
            index !== stories.length - 1 ? 'border-b border-[#eceff4]' : ''
          }`}
        >
          <div>
            <div className="text-sm font-semibold text-[#98a1af]">{story.index}</div>
            <div className="mt-4 text-[24px] font-semibold leading-[1.25] tracking-[-0.04em] text-[#111827]">
              {story.title}
            </div>
            <div className="mt-3 text-[16px] leading-8 text-[#5b6472]">{story.description}</div>
          </div>
          <div>{story.visual}</div>
        </div>
      ))}
    </div>
  );
}

function FaqList() {
  return (
    <div className="rounded-[30px] border border-[#e4e7ee] bg-white shadow-[0_20px_50px_rgba(15,23,42,0.05)]">
      {faqs.map((item, index) => (
        <details
          key={item.question}
          className={`group px-6 py-5 ${index !== faqs.length - 1 ? 'border-b border-[#eceff4]' : ''}`}
        >
          <summary className="flex cursor-pointer list-none items-center justify-between gap-6 text-[20px] font-semibold leading-[1.4] tracking-[-0.03em] text-[#111827]">
            {item.question}
            <span className="text-[#98a1af] transition-transform duration-200 group-open:rotate-45">
              +
            </span>
          </summary>
          <p className="mt-4 max-w-[860px] text-[16px] leading-8 text-[#5b6472]">
            {item.answer}
          </p>
        </details>
      ))}
    </div>
  );
}

export default function HomePage() {
  return (
    <main className="min-h-screen bg-[#f8f8f3] text-[#111827]">
      <div className="mx-auto max-w-[1760px] px-8 py-6 lg:px-14 lg:py-8">
        <header className="flex flex-wrap items-center justify-between gap-6 border-b border-[#e8e8e1] pb-6">
          <PublicBrand />
          <div className="hidden items-center gap-8 text-sm font-semibold text-[#5e6572] lg:flex">
            <a href="#why-now" className="transition-colors hover:text-[#111827]">
              为什么现在
            </a>
            <a href="#how-it-works" className="transition-colors hover:text-[#111827]">
              如何使用
            </a>
            <a href="#agent" className="transition-colors hover:text-[#111827]">
              Agent 优势
            </a>
            <a href="#faq" className="transition-colors hover:text-[#111827]">
              FAQ
            </a>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href="/auth?mode=login"
              className="inline-flex h-11 items-center rounded-full border border-[#d8dce5] bg-white px-5 text-sm font-semibold text-[#111827]"
            >
              登录
            </Link>
            <Link
              href="/auth?mode=apply"
              className="inline-flex h-11 items-center gap-2 rounded-full bg-[#111827] px-5 text-sm font-semibold text-white"
            >
              申请体验
              <RiArrowRightUpLine className="h-4 w-4" />
            </Link>
          </div>
        </header>

        <section className="grid gap-14 py-16 lg:grid-cols-[minmax(0,0.86fr)_minmax(780px,1.14fr)] lg:items-center lg:gap-18 lg:py-24">
          <div className="max-w-[840px]">
            <SectionTag>
              <RiGlobalLine className="h-4 w-4 text-[#4f46e5]" />
              {trackedPlatforms.join(' / ')}
            </SectionTag>
            <h1 className="mt-8 max-w-[920px] text-[clamp(3.15rem,5vw,5.55rem)] font-semibold leading-[1.01] tracking-[-0.085em] text-[#111827]">
              让品牌进入 AI 的推荐答案
            </h1>
            <p className="mt-6 max-w-[760px] text-[19px] leading-[1.92] text-[#5b6472]">
              基线分析先看整体位置，用户画像分析继续聚焦场景，再判断哪些来源真正影响 AI 的推荐。
            </p>
            <div className="mt-10 flex flex-wrap gap-3">
              <Link
                href="/auth?mode=apply"
                className="inline-flex h-12 items-center gap-2 rounded-full bg-[#111827] px-6 text-sm font-semibold text-white"
              >
                申请体验
                <RiArrowRightUpLine className="h-4 w-4" />
              </Link>
              <a
                href="#how-it-works"
                className="inline-flex h-12 items-center rounded-full border border-[#d8dce5] bg-white px-6 text-sm font-semibold text-[#111827]"
              >
                查看如何使用
              </a>
            </div>
          </div>
          <HeroPreview />
        </section>

        <section
          id="why-now"
          className="border-t border-[#e8e8e1] py-16 lg:py-20"
        >
          <div className="max-w-[900px]">
            <SectionTag>
              <RiCompass3Line className="h-4 w-4 text-[#4f46e5]" />
              为什么现在
            </SectionTag>
            <h2 className="mt-5 max-w-[900px] text-[38px] font-semibold leading-[1.15] tracking-[-0.06em] text-[#111827] lg:text-[52px]">
              AI 已经在替客户回答，品牌可见性正在被重新分配
            </h2>
            <p className="mt-5 max-w-[760px] text-[18px] leading-[1.95] text-[#5b6472]">
              不做监测，不代表风险不存在。它只会先出现在 AI 的回答里，再出现在你的业务结果里。
            </p>
          </div>
          <div className="mt-12">
            <WhyNowShowcase />
          </div>
        </section>

        <section
          id="how-it-works"
          className="border-t border-[#e8e8e1] py-16 lg:py-20"
        >
          <div className="max-w-[900px]">
            <SectionTag>
              <RiChat3Line className="h-4 w-4 text-[#4f46e5]" />
              如何使用
            </SectionTag>
            <h2 className="mt-5 max-w-[860px] text-[38px] font-semibold leading-[1.15] tracking-[-0.06em] text-[#111827] lg:text-[52px]">
              三步建立品牌可见分析
            </h2>
            <p className="mt-5 max-w-[720px] text-[18px] leading-[1.95] text-[#5b6472]">
              不是先看一堆指标，而是按基线、场景和来源三层，逐步逼近真正影响推荐的因素。
            </p>
          </div>
          <div className="mt-12">
            <WorkflowGrid />
          </div>
        </section>

        <section className="border-t border-[#e8e8e1] py-16 lg:py-20">
          <div className="max-w-[900px]">
            <SectionTag>
              <RiRadarLine className="h-4 w-4 text-[#4f46e5]" />
              监控与分析
            </SectionTag>
            <h2 className="mt-5 max-w-[900px] text-[38px] font-semibold leading-[1.15] tracking-[-0.06em] text-[#111827] lg:text-[52px]">
              基线、场景与来源，在同一套分析面板里展开
            </h2>
            <p className="mt-5 max-w-[760px] text-[18px] leading-[1.95] text-[#5b6472]">
              从全景掌控到场景聚焦，再到来源可信度判断，关键分析都能在一条链路里完成。
            </p>
          </div>
          <div className="mt-12">
            <MonitoringLogicShowcase />
          </div>
        </section>

        <section
          id="agent"
          className="border-t border-[#e8e8e1] py-16 lg:py-20"
        >
          <div>
            <SectionTag>
              <RiSparklingLine className="h-4 w-4 text-[#4f46e5]" />
              核心能力
            </SectionTag>
            <h2 className="mt-5 max-w-[1180px] text-[40px] font-semibold leading-[1.12] tracking-[-0.06em] text-[#111827] lg:text-[68px]">
              从基线到交付，全程由 Agent 推进
            </h2>
            <p className="mt-6 max-w-[920px] text-[19px] leading-[1.95] text-[#5b6472]">
              Specta 会把基线分析、用户画像分析和引用源置信度判断，持续推进成一份可继续追问的交付物。
            </p>
          </div>
          <div className="mt-12 space-y-6">
            <AgentOrchestrationMock />
            <AgentCapabilityStories />
            <CapabilityGrid />
          </div>
        </section>

        <section
          id="faq"
          className="border-t border-[#e8e8e1] py-16 lg:py-20"
        >
          <div className="max-w-[900px]">
            <SectionTag>
              <RiRadarLine className="h-4 w-4 text-[#4f46e5]" />
              FAQ
            </SectionTag>
            <h2 className="mt-5 text-[38px] font-semibold leading-[1.15] tracking-[-0.06em] text-[#111827] lg:text-[52px]">
              你最可能先问的问题
            </h2>
          </div>
          <div className="mt-12">
            <FaqList />
          </div>
        </section>

        <footer className="border-t border-[#e8e8e1] py-10">
          <div className="flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <PublicBrand textSizeClassName="text-[26px]" />
              <p className="mt-4 max-w-[420px] text-[15px] leading-7 text-[#5b6472]">
                追踪品牌在 AI 回答里的提及、引用和主题表现。
              </p>
            </div>
            <div className="grid gap-8 text-sm text-[#5b6472] sm:grid-cols-3">
              <div className="space-y-3">
                <div className="font-semibold text-[#111827]">产品</div>
                <a href="#why-now" className="block transition-colors hover:text-[#111827]">
                  为什么现在
                </a>
                <a href="#how-it-works" className="block transition-colors hover:text-[#111827]">
                  如何使用
                </a>
              </div>
              <div className="space-y-3">
                <div className="font-semibold text-[#111827]">体验</div>
                <Link
                  href="/auth?mode=apply"
                  className="block transition-colors hover:text-[#111827]"
                >
                  申请体验
                </Link>
                <Link
                  href="/auth?mode=login"
                  className="block transition-colors hover:text-[#111827]"
                >
                  登录
                </Link>
              </div>
              <div className="space-y-3">
                <div className="font-semibold text-[#111827]">支持</div>
                <a href="#faq" className="block transition-colors hover:text-[#111827]">
                  FAQ
                </a>
                <span className="block">support@specta.ai</span>
              </div>
            </div>
          </div>
        </footer>
      </div>
    </main>
  );
}
