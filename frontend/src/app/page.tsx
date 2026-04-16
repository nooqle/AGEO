import Link from 'next/link';
import type { ReactNode } from 'react';
import {
  RiArrowRightUpLine,
  RiChat3Line,
  RiCompass3Line,
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
    title: '品牌全景分析',
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
    title: '品牌全景分析 · 全景掌控',
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
    question: '品牌全景分析会先告诉我什么？',
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
    question: '为什么强调分析会持续推进？',
    answer:
      '因为 Specta 不是停在一张静态报告上。系统会在同一条对话里继续抓取、追问、判断，并把结果推进成交付物。',
  },
  {
    question: '如何获得邀请码？',
    answer:
      '先提交公司信息并验证邮箱。我们会向登记邮箱不定期发放邀请码，收到后即可进入平台。',
  },
];

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
        <div className="rounded-[24px] border border-[#eceff4] bg-[#fbfbfd] p-5 lg:row-span-2">
          <div className="flex items-center justify-between text-xs uppercase tracking-[0.18em] text-[#8d95a4]">
            <span>真实回答</span>
            <span>对话快照</span>
          </div>
          <div className="mt-5 space-y-4">
            <div className="rounded-[18px] border border-[#eceff4] bg-white px-4 py-3 text-sm leading-7 text-[#344054] shadow-[0_12px_28px_rgba(15,23,42,0.04)]">
              25 万预算的家用纯电 SUV 怎么选？
            </div>
            <div className="rounded-[20px] border border-[#e8ebf2] bg-[#eef2ff] px-4 py-4 text-sm leading-7 text-[#354152]">
              AI 回答优先提到 <span className="font-semibold text-[#111827]">某汽车品牌</span>，
              在家庭场景里仍然把 <span className="font-semibold text-[#111827]">竞品品牌</span>{' '}
              放在更靠前的位置，并引用了两家汽车媒体。
            </div>
            <div className="rounded-[18px] border border-[#dbe4f3] bg-white px-4 py-4 text-sm leading-7 text-[#475467]">
              已识别出 <span className="font-semibold text-[#111827]">品牌被提及</span>、<span className="font-semibold text-[#111827]">竞品压制</span> 与 <span className="font-semibold text-[#111827]">媒体引用</span>，正在继续生成用户画像场景分析报告。
            </div>
          </div>
          <div className="mt-5 flex flex-wrap gap-2">
            {['品牌被提及', '竞品压制', '媒体引用'].map((item) => (
              <span
                key={item}
                className="rounded-full border border-[#e4e7ee] bg-white px-3 py-1.5 text-xs font-medium text-[#5b6472]"
              >
                {item}
              </span>
            ))}
          </div>
        </div>

        <div className="rounded-[22px] bg-[#f7f8fb] px-5 py-5">
          <div className="flex items-center justify-between">
            <div className="text-xs uppercase tracking-[0.18em] text-[#8d95a4]">用户画像场景分析报告</div>
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
    <div className="grid gap-8 lg:grid-cols-[340px_minmax(0,1fr)] lg:gap-10">
      <div>
        <div className="max-w-[720px] text-[18px] leading-[1.95] text-[#5b6472]">
          Specta 不把问题讲成抽象风险，而是直接拆开三个判断：
          整体有没有被看见，关键场景是不是被竞品抢走，以及哪些来源正在左右 AI 的推荐。
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
                    <div className="text-[24px] font-semibold leading-[1.2] tracking-[-0.05em] text-[#111827]">
                      {item.title}
                      <span className="ml-3 text-[18px] font-medium tracking-[-0.03em] text-[#7b8494]">
                        {item.subtitle}
                      </span>
                    </div>
                    <div className="mt-2 text-[16px] leading-8 text-[#5b6472]">
                      {item.description}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="rounded-[32px] border border-[#e7e9ef] bg-white shadow-[0_24px_60px_rgba(15,23,42,0.06)]">
        <div className="grid gap-0 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="border-b border-[#eceff4] px-6 py-6 lg:border-b-0 lg:border-r">
            <div className="text-sm font-semibold text-[#a0a7b4]">真实问答场景</div>
            <div className="mt-5 rounded-[24px] bg-[#fbfbfd] p-5">
              <div className="max-w-[88%] rounded-[18px] bg-white px-4 py-4 text-[16px] leading-8 text-[#334155] shadow-[0_10px_24px_rgba(15,23,42,0.05)]">
                25 万预算的家用纯电 SUV 怎么选？
              </div>
              <div className="mt-4 rounded-[22px] border border-[#eceff4] bg-white px-5 py-5 shadow-[0_14px_32px_rgba(15,23,42,0.04)]">
                <div className="text-sm font-semibold text-[#7b8494]">AI 回答</div>
                <div className="mt-3 text-[16px] leading-8 text-[#374151]">
                  回答先提到 <span className="font-semibold text-[#111827]">竞品品牌</span>，再补充{' '}
                  <span className="font-semibold text-[#111827]">某汽车品牌</span>，并引用了两家汽车媒体与一个参数库。
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  {['竞品更靠前', '媒体引用', '参数库引用'].map((tag) => (
                    <span
                      key={tag}
                      className="rounded-full bg-[#f4f6fb] px-3 py-1.5 text-xs font-semibold text-[#4b5563]"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
              <div className="mt-4 rounded-[18px] border border-[#f4d9b7] bg-[#fff7ed] px-4 py-4 text-[15px] leading-7 text-[#9a5c1d]">
                如果不做基线、场景和来源三层判断，这类偏移通常只会在业务结果里被看到。
              </div>
            </div>
          </div>

          <div className="px-6 py-6">
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-[#a0a7b4]">同一条结果，拆成三层判断</div>
              <div className="rounded-full bg-[#111827] px-3 py-1 text-xs font-semibold text-white">
                Specta 输出
              </div>
            </div>
            <div className="mt-5 grid gap-3 sm:grid-cols-3">
              {[
                ['品牌提及率', '41.7%', '基线'],
                ['家庭场景缺口', '2 个', '画像'],
                ['高置信来源', '3 类', '来源'],
              ].map(([label, value, tag]) => (
                <div key={label} className="rounded-[20px] bg-[#fbfbfd] px-4 py-4">
                  <div className="flex items-center justify-between">
                    <div className="text-xs text-[#7b8494]">{label}</div>
                    <span className="rounded-full bg-white px-2.5 py-1 text-[11px] font-semibold text-[#5b6472]">
                      {tag}
                    </span>
                  </div>
                  <div className="mt-3 text-[28px] font-semibold tracking-[-0.05em] text-[#111827]">
                    {value}
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <div className="rounded-[20px] border border-[#eceff4] bg-white px-4 py-4">
                <div className="text-sm font-semibold text-[#111827]">品牌全景分析</div>
                <div className="mt-2 text-sm leading-7 text-[#5b6472]">先判断品牌在 4 个平台里的整体位置。</div>
                <div className="mt-4 h-2 rounded-full bg-[#edf1f5]">
                  <div className="h-2 rounded-full bg-[#111827]" style={{ width: '42%' }} />
                </div>
              </div>
              <div className="rounded-[20px] border border-[#eceff4] bg-white px-4 py-4">
                <div className="text-sm font-semibold text-[#111827]">用户画像分析</div>
                <div className="mt-2 text-sm leading-7 text-[#5b6472]">再拆出家庭、智驾、对比等关键场景。</div>
                <div className="mt-4 flex flex-wrap gap-2">
                  {['家庭', '智驾', '对比'].map((tag) => (
                    <span
                      key={tag}
                      className="rounded-full bg-[#eef2ff] px-2.5 py-1 text-xs font-semibold text-[#4f46e5]"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
              <div className="rounded-[20px] border border-[#eceff4] bg-white px-4 py-4">
                <div className="text-sm font-semibold text-[#111827]">引用源置信度</div>
                <div className="mt-2 text-sm leading-7 text-[#5b6472]">最后判断哪些来源真正影响推荐顺序。</div>
                <div className="mt-4 space-y-2">
                  {[
                    ['汽车媒体', '72%'],
                    ['参数库', '64%'],
                    ['垂直社区', '41%'],
                  ].map(([label, width]) => (
                    <div key={label}>
                      <div className="flex items-center justify-between text-xs text-[#7b8494]">
                        <span>{label}</span>
                        <span>{width}</span>
                      </div>
                      <div className="mt-1 h-2 rounded-full bg-[#edf1f5]">
                        <div className="h-2 rounded-full bg-[#111827]" style={{ width }} />
                      </div>
                    </div>
                  ))}
                </div>
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
    ['全景分析', '品牌档案', '已完成', '建立品牌与竞品上下文'],
    ['问题生成', '问题列表', '已生成', '输出高意图问题清单'],
    ['答案抓取', '答案抓取', '进行中', '从真实平台采集回答'],
    ['报告整理', '用户画像场景分析报告', '待更新', '沉淀报告并继续追问'],
  ] as const;

  return (
    <div className="rounded-[30px] border border-[#e4e7ee] bg-white px-6 py-6 shadow-[0_20px_50px_rgba(15,23,42,0.05)]">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,0.94fr)_minmax(0,1.06fr)]">
        <div className="rounded-[24px] border border-[#eceff4] bg-[#fbfbfd] p-5">
          <div className="flex items-center justify-between text-xs uppercase tracking-[0.18em] text-[#8d95a4]">
            <span>对话编排</span>
            <span>分析持续推进中</span>
          </div>
          <div className="mt-5 space-y-3">
            <div className="max-w-[82%] rounded-[18px] border border-[#eceff4] bg-white px-4 py-3 text-sm leading-7 text-[#344054]">
              帮我看一下某汽车品牌在高端纯电 SUV 场景里，哪些问题会先推荐竞品。
            </div>
            <div className="ml-auto max-w-[88%] rounded-[18px] border border-[#e8ebf2] bg-[#eef2ff] px-4 py-4 text-sm leading-7 text-[#344054]">
              已识别出 12 个问题，正在抓取 4 个平台的真实回答。我会继续定位负向提及、竞品压制与主题缺口。
            </div>
          </div>
          <div className="mt-5 grid gap-3 sm:grid-cols-3">
            {[
              ['当前任务', '竞品压制定位'],
              ['运行状态', '答案抓取 -> 报告生成'],
              ['交付方式', '对话 + 工作台'],
            ].map(([label, value]) => (
              <div
                key={label}
                className="rounded-[18px] border border-[#eceff4] bg-white px-4 py-4"
              >
                <div className="text-xs text-[#7b8494]">{label}</div>
                <div className="mt-2 text-base font-semibold text-[#111827]">{value}</div>
              </div>
            ))}
          </div>
          <div className="mt-5 flex flex-wrap gap-2">
            {['继续追问', '负向提及', '竞品压制', '主题缺口'].map((tag) => (
              <span
                key={tag}
                className="rounded-full border border-[#e4e7ee] bg-white px-3 py-1 text-xs text-[#5b6472]"
              >
                {tag}
              </span>
            ))}
          </div>
        </div>

        <div className="rounded-[24px] border border-[#eceff4] bg-[#fbfbfd] p-5">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs uppercase tracking-[0.18em] text-[#8d95a4]">执行面板</div>
              <div className="mt-2 text-[22px] font-semibold tracking-[-0.04em] text-[#111827]">
                同一条对话，持续推进整条分析链
              </div>
            </div>
            <div className="rounded-full bg-[#eef2ff] px-3 py-1 text-xs font-semibold text-[#4f46e5]">
              实时流转
            </div>
          </div>
          <div className="mt-6 space-y-3">
            {nodes.map(([agentLabel, label, detail, description], index) => (
              <div
                key={agentLabel}
                className="rounded-[20px] border border-[#eceff4] bg-white px-4 py-4"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-3">
                    <div className="rounded-full bg-[#111827] px-3 py-1 text-xs font-semibold text-white">
                      {agentLabel}
                    </div>
                    <div>
                      <div className="text-[16px] font-semibold text-[#111827]">{label}</div>
                      <div className="mt-1 text-sm leading-7 text-[#5b6472]">{description}</div>
                    </div>
                  </div>
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-semibold ${
                      index < 2
                        ? 'bg-[#dcfce7] text-[#166534]'
                        : index === 2
                          ? 'bg-[#eef2ff] text-[#4f46e5]'
                          : 'bg-[#f4f0fb] text-[#7c68c2]'
                    }`}
                  >
                    {detail}
                  </span>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div className="rounded-[18px] bg-white px-4 py-4">
              <div className="text-xs text-[#7b8494]">已生成交付物</div>
              <div className="mt-3 space-y-2">
                {['品牌档案', '基线问题列表', '答案抓取结果'].map((item) => (
                  <div key={item} className="rounded-[14px] bg-[#fbfbfd] px-3 py-3 text-sm font-semibold text-[#111827]">
                    {item}
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-[18px] bg-white px-4 py-4">
              <div className="text-xs text-[#7b8494]">当前推进</div>
              <div className="mt-3 rounded-[16px] bg-[#fbfbfd] px-4 py-4">
                <div className="text-sm font-semibold text-[#111827]">正在定位高意图家庭场景</div>
                <div className="mt-2 text-sm leading-7 text-[#5b6472]">
                  系统会把竞品压制最明显的问法补进报告，并继续支持追问。
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function AgentCapabilityStories() {
  const stories = [
    {
      index: '01',
      title: '从对话里发起品牌全景分析',
      description: '用户直接在对话里提出分析目标，系统识别意图后生成问题并启动全景分析。',
      visual: (
        <div className="space-y-3 rounded-[22px] border border-[#e6eaf0] bg-[#fbfbfd] p-4">
          <div className="max-w-[82%] rounded-[16px] border border-[#eceff4] bg-white px-4 py-3 text-sm leading-6 text-[#344054]">
            先做一轮品牌全景分析，看看某汽车品牌在 4 个 AI 平台里的整体位置。
          </div>
          <div className="ml-auto max-w-[88%] rounded-[16px] border border-[#e8ebf2] bg-[#eef2ff] px-4 py-3 text-sm leading-6 text-[#344054]">
            已生成问题列表，正在进入答案抓取，采集 4 个平台的真实回答。
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            {[
              ['品牌档案', '已完成'],
              ['问题列表', '已生成'],
              ['答案抓取', '准备中'],
            ].map(([label, status]) => (
              <div key={label} className="rounded-[16px] border border-[#eceff4] bg-white px-4 py-3">
                <div className="text-xs text-[#7b8494]">{label}</div>
                <div className="mt-2 text-sm font-semibold text-[#111827]">{status}</div>
              </div>
            ))}
          </div>
        </div>
      ),
    },
    {
      index: '02',
      title: '真实回答采集，而不是静态估计',
      description: '对同一组问题持续抓取真实平台回答，直接记录品牌提及、竞品压制和引用来源。',
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
    {
      index: '03',
      title: '引用源置信度直接在结果里判断',
      description: '不是只告诉你“引用了谁”，而是拆开来源类型、平台偏好和可信度层级。',
      visual: (
        <div className="rounded-[22px] border border-[#e6eaf0] bg-[#fbfbfd] p-4">
          <div className="grid gap-3 sm:grid-cols-[1.05fr_0.95fr]">
            <div className="rounded-[18px] bg-white px-4 py-4">
              <div className="text-sm font-semibold text-[#111827]">来源分层</div>
              <div className="mt-4 space-y-3">
                {[
                  ['汽车媒体', '高', '72%'],
                  ['参数库', '高', '64%'],
                  ['垂直社区', '中', '41%'],
                ].map(([label, level, value]) => (
                  <div key={label}>
                    <div className="flex items-center justify-between text-sm">
                      <span className="font-semibold text-[#111827]">{label}</span>
                      <span className="text-[#7b8494]">{level}</span>
                    </div>
                    <div className="mt-2 h-2 rounded-full bg-[#edf1f5]">
                      <div className="h-2 rounded-full bg-[#111827]" style={{ width: value }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-[18px] bg-white px-4 py-4">
              <div className="text-sm font-semibold text-[#111827]">平台偏好</div>
              <div className="mt-4 space-y-3">
                {[
                  ['豆包', '媒体 / 视频'],
                  ['Kimi', '媒体 / 参数库'],
                  ['元宝', '媒体 / 社区'],
                ].map(([platform, mix]) => (
                  <div key={platform} className="rounded-[14px] bg-[#fbfbfd] px-3 py-3">
                    <div className="text-sm font-semibold text-[#111827]">{platform}</div>
                    <div className="mt-1 text-sm text-[#5b6472]">{mix}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      ),
    },
    {
      index: '04',
      title: '交付物会继续更新，不是停在一张报告',
      description: '基线、画像、来源判断都会沉淀成交付物，并继续回到对话里追问和协作。',
      visual: (
        <div className="rounded-[22px] border border-[#e6eaf0] bg-[#fbfbfd] p-4">
          <div className="grid gap-3 sm:grid-cols-[1.1fr_0.9fr]">
            <div className="rounded-[18px] border border-[#e8ebf2] bg-white px-4 py-4">
              <div className="text-xs uppercase tracking-[0.18em] text-[#8d95a4]">交付物工作台</div>
              <div className="mt-4 space-y-3">
                {[
                  ['基线问题列表', '已生成'],
                  ['AI 答案抓取结果', '已完成'],
                  ['用户画像场景分析报告', '持续更新'],
                ].map(([name, status]) => (
                  <div key={name} className="rounded-[16px] border border-[#eceff4] bg-[#fbfbfd] px-4 py-3">
                    <div className="text-sm font-semibold text-[#111827]">{name}</div>
                    <div className="mt-1 text-xs text-[#7b8494]">{status}</div>
                  </div>
                ))}
              </div>
            </div>
            <div className="space-y-3 rounded-[18px] bg-white px-4 py-4">
              <div className="text-sm font-semibold text-[#111827]">后续追问</div>
              <div className="rounded-[14px] bg-[#fbfbfd] px-3 py-3 text-sm leading-6 text-[#344054]">
                继续帮我拆一下高意图家庭场景里，哪些回答更偏向竞品。
              </div>
              <div className="rounded-[14px] border border-[#eceff4] px-3 py-3 text-sm leading-6 text-[#344054]">
                已定位 2 个竞品压制最明显的问法，并补充到报告里。
              </div>
            </div>
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
          <summary className="grid cursor-pointer list-none grid-cols-[minmax(0,1fr)_20px] items-center gap-5 text-[18px] font-semibold leading-[1.45] tracking-[-0.03em] text-[#111827] lg:text-[20px]">
            <span className="min-w-0 break-keep pr-2">{item.question}</span>
            <span className="text-[#98a1af] transition-transform duration-200 group-open:rotate-45">
              +
            </span>
          </summary>
          <p className="mt-4 max-w-[1080px] text-[16px] leading-8 text-[#5b6472]">
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
              持续推进
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
              品牌全景分析先看整体位置，用户画像分析继续聚焦场景，再判断哪些来源真正影响 AI 的推荐。
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
              客户先问 AI，再决定联系谁
            </h2>
            <p className="mt-5 max-w-[760px] text-[18px] leading-[1.95] text-[#5b6472]">
              Specta 把整体位置、关键场景和来源可信度拆开给你看，不让偏移只在业务结果里暴露。
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
              三步完成品牌可见分析
            </h2>
            <p className="mt-5 max-w-[720px] text-[18px] leading-[1.95] text-[#5b6472]">
              先看全景，再看场景，最后判断来源可信度。
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
              基线、场景与来源，在同一套面板里展开
            </h2>
            <p className="mt-5 max-w-[760px] text-[18px] leading-[1.95] text-[#5b6472]">
              一套面板，连续看清整体位置、关键场景和来源判断。
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
            分析会在一条对话里持续推进
          </h2>
          <p className="mt-6 max-w-[920px] text-[19px] leading-[1.95] text-[#5b6472]">
            不停在一张报告上，而是继续抓取、继续追问、继续更新交付物。
            </p>
          </div>
          <div className="mt-12 space-y-6">
            <AgentOrchestrationMock />
            <AgentCapabilityStories />
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
