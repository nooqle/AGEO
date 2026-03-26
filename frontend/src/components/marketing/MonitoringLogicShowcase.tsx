'use client';

import { useMemo, useState } from 'react';
import {
  RiBarChartBoxLine,
  RiChat3Line,
  RiRadarLine,
} from '@remixicon/react';

type ShowcaseKey = 'baseline' | 'persona' | 'sources';

const showcaseItems: Array<{
  key: ShowcaseKey;
  title: string;
  description: string;
  icon: typeof RiRadarLine;
}> = [
  {
    key: 'baseline',
    title: '基线分析',
    description: '先看品牌在多平台回答中的提及、引用和主题覆盖。',
    icon: RiRadarLine,
  },
  {
    key: 'persona',
    title: '用户画像分析',
    description: '按用户画像和场景聚焦高价值问题，定位更关键的回答入口。',
    icon: RiBarChartBoxLine,
  },
  {
    key: 'sources',
    title: '引用源置信度',
    description: '判断哪些来源更可信，哪些来源真正影响 AI 的推荐结果。',
    icon: RiChat3Line,
  },
];

function BaselinePanel() {
  const bars = [
    ['DeepSeek', '72%', '#4f6af7'],
    ['Kimi', '80%', '#7c4dff'],
    ['豆包', '90%', '#11c76f'],
    ['元宝', '98%', '#8b5cf6'],
  ] as const;

  return (
    <div className="grid h-full gap-0 lg:grid-cols-[0.92fr_1.08fr]">
      <div className="border-b border-[#eceff4] px-8 py-8 lg:border-b-0 lg:border-r">
        <div className="text-[18px] font-semibold text-[#111827]">基线分析，先看整体位置</div>
        <p className="mt-4 max-w-[320px] text-[18px] leading-[1.9] text-[#5b6472]">
          先建立品牌在主流 AI 平台里的基线，确认提及率、引用分布和主题覆盖处在哪个位置。
        </p>
        <div className="mt-10 grid gap-3">
          {[
            ['品牌提及率', '41.7%'],
            ['内容引用率', '100%'],
            ['主题覆盖', '10 / 12'],
          ].map(([label, value]) => (
            <div key={label} className="rounded-[18px] bg-[#fbfbfd] px-4 py-4">
              <div className="text-xs text-[#7b8494]">{label}</div>
              <div className="mt-2 text-[26px] font-semibold tracking-[-0.05em] text-[#111827]">
                {value}
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="px-8 py-8">
        <div className="text-[18px] font-semibold text-[#111827]">AI 可见性</div>
        <div className="mt-5 flex h-[320px] items-end justify-between gap-8 rounded-[24px] bg-[#fcfcfd] px-8 pb-8 pt-10">
          {bars.map(([label, height, color]) => (
            <div key={label} className="flex flex-1 flex-col items-center justify-end gap-4">
              <div className="text-sm text-[#94a3b8]">{height}</div>
              <div
                className="w-full max-w-[72px] rounded-[22px]"
                style={{ height, backgroundColor: color }}
              />
              <div className="text-sm font-semibold text-[#4b5563]">{label}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function PersonaPanel() {
  const personas = [
    ['高端家庭', '纯电 SUV', '品牌已建立认知'],
    ['智驾通勤', '城市 NOA', '品牌具备优势'],
    ['科技尝鲜', '车型对比', '容易被竞品挤压'],
  ] as const;

  return (
    <div className="grid h-full gap-0 lg:grid-cols-[0.92fr_1.08fr]">
      <div className="border-b border-[#eceff4] px-8 py-8 lg:border-b-0 lg:border-r">
        <div className="text-[18px] font-semibold text-[#111827]">用户画像分析，聚焦关键场景</div>
        <p className="mt-4 max-w-[320px] text-[18px] leading-[1.9] text-[#5b6472]">
          不是所有问题都同样重要。先按用户画像和场景拆开，找到最值得抢占的问答入口。
        </p>
      </div>
      <div className="grid gap-4 px-8 py-8 sm:grid-cols-3">
        {personas.map(([persona, scene, status]) => (
          <div key={persona} className="rounded-[24px] border border-[#eceff4] bg-[#fbfbfd] px-5 py-6">
            <div className="text-sm font-semibold text-[#111827]">{persona}</div>
            <div className="mt-3 text-[20px] font-semibold tracking-[-0.04em] text-[#111827]">
              {scene}
            </div>
            <div className="mt-4 rounded-full bg-white px-3 py-2 text-sm text-[#5b6472]">{status}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function SourcesPanel() {
  const rows = [
    ['汽车媒体', '高', '被多个平台高频引用'],
    ['参数库', '高', '用于车型参数和配置判断'],
    ['垂直社区', '中', '适合补充真实口碑'],
    ['短视频/泛内容', '低', '波动更大'],
  ] as const;

  return (
    <div className="grid h-full gap-0 lg:grid-cols-[0.92fr_1.08fr]">
      <div className="border-b border-[#eceff4] px-8 py-8 lg:border-b-0 lg:border-r">
        <div className="text-[18px] font-semibold text-[#111827]">引用源置信度，判断谁在影响回答</div>
        <p className="mt-4 max-w-[320px] text-[18px] leading-[1.9] text-[#5b6472]">
          不只是看引用了谁，还要判断这些来源的可信度和影响力，知道该补什么内容。
        </p>
      </div>
      <div className="px-8 py-8">
        <div className="rounded-[24px] border border-[#eceff4] bg-[#fcfcfd]">
          <div className="grid grid-cols-[1.1fr_0.6fr_1.3fr] border-b border-[#eceff4] px-5 py-4 text-sm font-semibold text-[#7b8494]">
            <div>来源类型</div>
            <div>等级</div>
            <div>判断</div>
          </div>
          {rows.map(([source, level, status]) => (
            <div
              key={source}
              className="grid grid-cols-[1.1fr_0.6fr_1.3fr] border-b border-[#eceff4] px-5 py-4 text-[16px] leading-7 text-[#374151] last:border-b-0"
            >
              <div className="font-semibold text-[#111827]">{source}</div>
              <div>{level}</div>
              <div>{status}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function MonitoringLogicShowcase() {
  const [active, setActive] = useState<ShowcaseKey>('baseline');

  const activeItem = useMemo(
    () => showcaseItems.find((item) => item.key === active) ?? showcaseItems[0],
    [active],
  );

  return (
    <div className="rounded-[36px] border border-[#eceff4] bg-[repeating-linear-gradient(135deg,rgba(236,239,244,0.45),rgba(236,239,244,0.45)_2px,transparent_2px,transparent_10px)] p-8 lg:p-10">
      <div className="grid gap-8 lg:grid-cols-[320px_minmax(0,1fr)] lg:items-center">
        <div>
          <div className="rounded-[26px] bg-white px-5 py-5 text-[18px] leading-[1.85] text-[#384152] shadow-[0_16px_40px_rgba(15,23,42,0.04)]">
            {activeItem.description}
          </div>
          <div className="mt-4 space-y-3">
            {showcaseItems.map((item) => {
              const Icon = item.icon;
              const isActive = item.key === active;
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setActive(item.key)}
                  className={`flex w-fit items-center gap-3 rounded-[22px] border px-5 py-4 text-left text-[18px] font-semibold transition-all ${
                    isActive
                      ? 'border-[#d8dce5] bg-white text-[#111827] shadow-[0_12px_28px_rgba(15,23,42,0.04)]'
                      : 'border-[#eceff4] bg-white/78 text-[#374151]'
                  }`}
                >
                  <span className="flex h-9 w-9 items-center justify-center rounded-full border border-[#e6e8ef] bg-[#fafaf9]">
                    <Icon className="h-5 w-5" />
                  </span>
                  {item.title}
                </button>
              );
            })}
          </div>
        </div>

        <div className="rounded-[30px] border border-[#e4e7ee] bg-white shadow-[0_20px_50px_rgba(15,23,42,0.05)]">
          {active === 'baseline' ? <BaselinePanel /> : null}
          {active === 'persona' ? <PersonaPanel /> : null}
          {active === 'sources' ? <SourcesPanel /> : null}
        </div>
      </div>
    </div>
  );
}
