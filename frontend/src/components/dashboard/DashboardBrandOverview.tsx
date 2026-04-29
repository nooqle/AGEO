'use client';

import { useState } from 'react';
import type { ComponentType, CSSProperties, ReactNode } from 'react';
import {
  RiArrowDownLine,
  RiArrowUpLine,
  RiBookmark3Line,
  RiBriefcase4Line,
  RiCalendarEventLine,
  RiGlobalLine,
  RiLeafLine,
  RiPriceTag3Line,
  RiShapesLine,
  RiTeamLine,
} from '@remixicon/react';
import { BrandAvatar } from './BrandAvatar';
import { DashboardSectionHeader } from './DashboardSectionHeader';
import { Skeleton } from '@/components/ui/skeleton';
import type { Entity } from '@/types/entity';
import type { WorkflowBrandProfile, WorkflowCompetitor } from '@/types/canvas';

interface DashboardBrandOverviewProps {
  entity: Entity;
  archive?: DashboardBrandArchiveData | null;
  isLoading?: boolean;
}

export interface DashboardBrandArchiveData {
  brandProfile?: (WorkflowBrandProfile & { official_website?: string }) | null;
  competitors?: WorkflowCompetitor[] | null;
}

type CompetitorGroupKey = '直接竞争' | '间接竞争' | '潜在竞争';

const COMPETITOR_GROUP_META: Record<
  CompetitorGroupKey,
  {
    accent: string;
    surface: string;
    badge: string;
    text: string;
  }
> = {
  直接竞争: {
    accent: '#ef5b5b',
    surface: 'color-mix(in srgb, var(--bg-elevated) 90%, #f4e4e4 10%)',
    badge: 'color-mix(in srgb, var(--bg-elevated) 78%, #f0cfcf 22%)',
    text: '#d14a4a',
  },
  间接竞争: {
    accent: '#9e7445',
    surface: 'color-mix(in srgb, var(--bg-elevated) 92%, #efe3d0 8%)',
    badge: 'color-mix(in srgb, var(--bg-elevated) 82%, #e8d3b4 18%)',
    text: '#85623b',
  },
  潜在竞争: {
    accent: '#3f83f8',
    surface: 'color-mix(in srgb, var(--bg-elevated) 90%, #e2eaf4 10%)',
    badge: 'color-mix(in srgb, var(--bg-elevated) 80%, #d3dfef 20%)',
    text: '#3569d6',
  },
};

function normalizeCompetitionType(type?: string): CompetitorGroupKey {
  if (type === 'direct' || type === '直接' || type === '直接竞争') return '直接竞争';
  if (type === 'indirect' || type === '间接' || type === '间接竞争') return '间接竞争';
  return '潜在竞争';
}

function groupCompetitors(competitors: WorkflowCompetitor[] | undefined | null) {
  const grouped: Record<CompetitorGroupKey, WorkflowCompetitor[]> = {
    直接竞争: [],
    间接竞争: [],
    潜在竞争: [],
  };

  (competitors || []).forEach((competitor) => {
    grouped[normalizeCompetitionType(competitor.competition_type)].push(competitor);
  });

  (Object.keys(grouped) as CompetitorGroupKey[]).forEach((key) => {
    grouped[key] = grouped[key]
      .slice()
      .sort((a, b) => (b.relevance_score || 0) - (a.relevance_score || 0));
  });

  return grouped;
}

function TitleWithIcon({
  icon: Icon,
  children,
}: {
  icon: ComponentType<{ className?: string; style?: CSSProperties }>;
  children: ReactNode;
}) {
  return (
    <div className="flex items-center gap-2 text-[11px] font-medium tracking-[0.16em] text-[var(--text-tertiary)]">
      <Icon className="h-4 w-4" style={{ color: 'var(--text-secondary)' }} />
      <span>{children}</span>
    </div>
  );
}

function FieldLabel({
  icon: Icon,
  children,
}: {
  icon: ComponentType<{ className?: string; style?: CSSProperties }>;
  children: ReactNode;
}) {
  return (
    <div className="flex items-center gap-2 text-[11px] tracking-[0.12em] text-[var(--text-tertiary)]">
      <Icon className="h-3.5 w-3.5" style={{ color: 'var(--text-secondary)' }} />
      <span>{children}</span>
    </div>
  );
}

function DashboardBrandOverviewLoading() {
  return (
    <div className="grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
      <div className="dashboard-inner-panel rounded-[24px] px-5 py-5">
        <Skeleton width={112} height={16} animation="wave" />
        <div className="mt-4 flex items-start gap-4">
          <Skeleton variant="rounded" width={56} height={56} animation="wave" className="rounded-[18px]" />
          <div className="min-w-0 flex-1 space-y-3">
            <Skeleton width="42%" height={26} animation="wave" />
            <Skeleton width="34%" height={15} animation="wave" />
          </div>
        </div>
        <div className="mt-5 space-y-2">
          <Skeleton width="96%" height={14} animation="wave" />
          <Skeleton width="92%" height={14} animation="wave" />
          <Skeleton width="76%" height={14} animation="wave" />
        </div>
        <div className="mt-5 grid gap-3 md:grid-cols-2">
          <Skeleton height={96} animation="wave" className="rounded-[18px]" />
          <Skeleton height={96} animation="wave" className="rounded-[18px]" />
          <Skeleton height={78} animation="wave" className="rounded-[18px]" />
          <Skeleton height={78} animation="wave" className="rounded-[18px]" />
        </div>
      </div>

      <div className="dashboard-inner-panel rounded-[24px] px-5 py-5">
        <Skeleton width={96} height={16} animation="wave" />
        <div className="mt-5 space-y-3">
          <Skeleton height={96} animation="wave" className="rounded-[20px]" />
          <Skeleton height={96} animation="wave" className="rounded-[20px]" />
          <Skeleton height={96} animation="wave" className="rounded-[20px]" />
        </div>
      </div>
    </div>
  );
}

export function DashboardBrandOverview({ entity, archive, isLoading = false }: DashboardBrandOverviewProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const profile = archive?.brandProfile;
  const competitors = archive?.competitors || [];
  const groupedCompetitors = groupCompetitors(competitors);

  const description =
    profile?.description?.trim() ||
    entity.description?.trim() ||
    '当前还没有完整品牌档案内容，建议先完善品牌介绍、定位、受众和官网信息。';

  const website = profile?.official_website?.trim() || entity.domain?.trim();
  const displayName = profile?.brand_name?.trim() || entity.name;
  const displayNameEn = profile?.brand_name_en?.trim();
  const industry = profile?.industry?.trim() || entity.industry?.trim();
  const aliasTags = entity.aliases.filter(Boolean).slice(0, 5);
  const productTags = (profile?.core_products || []).filter(Boolean).slice(0, 6);

  return (
    <section
      className="dashboard-shell rounded-[30px] px-6 py-6"
    >
      <DashboardSectionHeader
        title="品牌档案与竞品分类"
        action={(
          <button
            type="button"
            onClick={() => setIsExpanded((current) => !current)}
            className="inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[13px] font-medium transition-colors"
            style={{
              borderColor: 'var(--border-subtle)',
              color: 'var(--text-secondary)',
              background: 'var(--bg-elevated)',
            }}
          >
            {isExpanded ? '收起品牌信息' : '展开品牌信息'}
            {isExpanded ? <RiArrowUpLine className="h-4 w-4" /> : <RiArrowDownLine className="h-4 w-4" />}
          </button>
        )}
      />

      {!isExpanded ? (
        <div
          className="dashboard-inner-panel rounded-[22px] px-4 py-4 text-[14px] leading-7"
          style={{ color: 'var(--text-secondary)' }}
          >
            {isLoading
              ? `${entity.name} 的品牌档案与竞品分类正在加载。`
              : `品牌档案与竞品分类已收起，可按需展开查看 ${displayName} 的品牌信息与竞品分类。`}
          </div>
      ) : isLoading ? (
        <DashboardBrandOverviewLoading />
      ) : (
        <div className="grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
          <div
            className="dashboard-inner-panel rounded-[24px] px-5 py-5"
          >
            <TitleWithIcon icon={RiBookmark3Line}>品牌档案</TitleWithIcon>

            <div className="mt-4 flex items-start gap-4">
              <BrandAvatar name={displayName} domain={website || entity.domain} size={56} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-[24px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">{displayName}</h2>
                  {displayNameEn ? (
                    <span className="text-[16px] text-[var(--text-secondary)]">{displayNameEn}</span>
                  ) : null}
                  {industry ? (
                    <span
                      className="rounded-full border px-2.5 py-1 text-[11px] font-medium"
                      style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-secondary)', background: 'var(--bg-tertiary)' }}
                    >
                      {industry}
                    </span>
                  ) : null}
                </div>

                {website ? (
                  <div className="mt-2 flex items-center gap-2 text-[13px] text-[var(--text-secondary)]">
                    <RiGlobalLine className="h-4 w-4" />
                    <a
                      href={website.startsWith('http') ? website : `https://${website}`}
                      target="_blank"
                      rel="noreferrer"
                      className="truncate underline-offset-2 hover:underline"
                    >
                      {website}
                    </a>
                  </div>
                ) : null}
              </div>
            </div>

            <p className="mt-5 text-[14px] leading-8 text-[var(--text-secondary)]">{description}</p>

            <div className="mt-5 grid gap-3 md:grid-cols-2">
              <div className="dashboard-inner-panel rounded-[18px] px-4 py-4">
                <FieldLabel icon={RiShapesLine}>品牌定位</FieldLabel>
                <div className="mt-2 text-[14px] leading-7 text-[var(--text-primary)]">{profile?.brand_positioning || '暂无定位信息'}</div>
              </div>
              <div className="dashboard-inner-panel rounded-[18px] px-4 py-4">
                <FieldLabel icon={RiTeamLine}>目标受众</FieldLabel>
                <div className="mt-2 text-[14px] leading-7 text-[var(--text-primary)]">{profile?.target_audience || '暂无受众信息'}</div>
              </div>
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <div className="dashboard-inner-panel rounded-[18px] px-4 py-4">
                <FieldLabel icon={RiPriceTag3Line}>价格带</FieldLabel>
                <div className="mt-2 text-[14px] font-medium text-[var(--text-primary)]">{profile?.price_positioning || '暂无价格带信息'}</div>
              </div>
              <div className="dashboard-inner-panel rounded-[18px] px-4 py-4">
                <FieldLabel icon={RiCalendarEventLine}>成立年份</FieldLabel>
                <div className="mt-2 text-[14px] font-medium text-[var(--text-primary)]">{profile?.founded_year || '暂无成立年份'}</div>
              </div>
            </div>

            {productTags.length > 0 ? (
              <div className="mt-4">
                <FieldLabel icon={RiBriefcase4Line}>核心产品</FieldLabel>
                <div className="mt-2 flex flex-wrap gap-2">
                  {productTags.map((product) => (
                    <span
                      key={product}
                      className="rounded-full border px-2.5 py-1 text-[11px] font-medium"
                      style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-secondary)', background: 'var(--bg-tertiary)' }}
                    >
                      {product}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}

            {aliasTags.length > 0 ? (
              <div className="mt-4">
                <FieldLabel icon={RiBookmark3Line}>别名</FieldLabel>
                <div className="mt-2 flex flex-wrap gap-2">
                  {aliasTags.map((alias) => (
                    <span
                      key={alias}
                      className="rounded-full border px-2.5 py-1 text-[11px] font-medium"
                      style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-secondary)', background: 'var(--bg-tertiary)' }}
                    >
                      {alias}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
          </div>

          <div
            className="dashboard-inner-panel rounded-[24px] px-5 py-5"
          >
            <TitleWithIcon icon={RiLeafLine}>竞品分类</TitleWithIcon>

            <div className="mt-5 space-y-3">
              {(['直接竞争', '间接竞争', '潜在竞争'] as CompetitorGroupKey[]).map((group) => {
                const items = groupedCompetitors[group];
                const meta = COMPETITOR_GROUP_META[group];
                return (
                  <div
                    key={group}
                    className="dashboard-inner-panel rounded-[20px] px-4 py-4"
                    style={{
                      background: meta.surface,
                      borderColor: 'color-mix(in srgb, var(--border-subtle) 72%, transparent 28%)',
                    }}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2 text-[17px] font-semibold text-[var(--text-primary)]">
                        <RiLeafLine className="h-4 w-4" style={{ color: meta.accent }} />
                        <span>{group}</span>
                      </div>
                      <div
                        className="rounded-full px-2.5 py-1 text-[12px] font-medium"
                        style={{ background: meta.badge, color: meta.text }}
                      >
                        {items.length} 个品牌
                      </div>
                    </div>

                    {items.length > 0 ? (
                      <div className="mt-3 flex flex-wrap gap-2.5">
                        {items.map((competitor, index) => (
                          <span
                            key={`${group}-${competitor.name}`}
                            className="inline-flex items-center gap-2 rounded-full border px-3.5 py-2 text-[13px] font-medium"
                            style={{
                              borderColor: 'color-mix(in srgb, transparent 42%, var(--border-subtle) 58%)',
                              background: `color-mix(in srgb, ${meta.badge} 72%, var(--bg-elevated) 28%)`,
                              color: 'var(--text-secondary)',
                            }}
                          >
                            <span
                              className="inline-flex h-6 min-w-6 items-center justify-center rounded-full px-1.5 text-[11px] font-semibold"
                              style={{ background: meta.badge, color: meta.text }}
                            >
                              #{index + 1}
                            </span>
                            <span className="text-[14px] font-semibold text-[var(--text-primary)]">
                              {competitor.name}
                            </span>
                          </span>
                        ))}
                      </div>
                    ) : (
                      <div className="mt-3 text-[13px] leading-6 text-[var(--text-tertiary)]">
                        当前产物里还没有识别到这一类竞品。
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
