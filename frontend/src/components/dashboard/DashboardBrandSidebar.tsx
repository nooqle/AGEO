'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { RiAddLine, RiGitBranchLine, RiSettings3Line } from '@remixicon/react';
import { BrandAvatar } from './BrandAvatar';
import { BrandManageDialog } from './BrandManageDialog';
import {
  cleanEntityDisplayText,
  splitDashboardEntities,
} from '@/lib/brandEntityHygiene';
import type { Entity } from '@/types/entity';

interface DashboardBrandSidebarProps {
  entities: Entity[];
  selectedBrandId: string | null;
  onSelectBrand: (brandId: string) => void;
  onAddBrand?: () => void;
  showBrandSpaceLink?: boolean;
}

export function DashboardBrandSidebar({
  entities,
  selectedBrandId,
  onSelectBrand,
  onAddBrand,
  showBrandSpaceLink = true,
}: DashboardBrandSidebarProps) {
  const router = useRouter();
  const [manageOpen, setManageOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const { primary, internal, duplicates } = splitDashboardEntities(
    entities,
    selectedBrandId,
  );
  void internal;
  const hiddenDuplicateCount = duplicates.length;

  return (
    <aside className="dashboard-shell sticky top-4 h-fit rounded-[18px] px-4 py-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[11px] font-medium tracking-[0.14em] text-[var(--text-tertiary)]">
            品牌
          </div>
          <h2 className="mt-1 text-[18px] font-semibold text-[var(--text-primary)]">品牌列表</h2>
        </div>
        <button
          type="button"
          onClick={() => setManageOpen(true)}
          className="inline-flex h-10 w-10 items-center justify-center rounded-lg border text-[var(--text-secondary)] transition-colors hover:border-[var(--brand-primary)] hover:text-[var(--brand-primary)]"
          style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-secondary)' }}
          aria-label="管理品牌"
          title="管理品牌"
        >
          <RiSettings3Line className="h-4 w-4" />
        </button>
      </div>

      <div className="mt-4 space-y-2">
        {primary.map((entity) => {
          const isSelected = entity.id === selectedBrandId;
          const name = cleanEntityDisplayText(entity.name, '未命名品牌');
          const domain = cleanEntityDisplayText(entity.domain, '未设置官网');
          return (
            <button
              key={entity.id}
              type="button"
              onClick={() => onSelectBrand(entity.id)}
              className="grid w-full grid-cols-[38px_minmax(0,1fr)] items-center gap-3 rounded-[14px] border px-3 py-3 text-left transition-colors"
              style={{
                borderColor: isSelected
                  ? 'color-mix(in srgb, var(--brand-primary) 46%, var(--border-subtle) 54%)'
                  : 'var(--border-subtle)',
                background: isSelected
                  ? 'color-mix(in srgb, var(--brand-bg) 70%, var(--bg-secondary) 30%)'
                  : 'var(--bg-secondary)',
              }}
            >
              <BrandAvatar name={name} domain={entity.domain} size={38} />
              <span className="min-w-0">
                <span className="block truncate text-[14px] font-semibold text-[var(--text-primary)]">
                  {name}
                </span>
                <span className="mt-0.5 block truncate text-[12px] text-[var(--text-tertiary)]">
                  {domain}
                </span>
              </span>
            </button>
          );
        })}

        {hiddenDuplicateCount ? (
          <div className="px-1 pt-1">
            <button
              type="button"
              className="text-left text-[12px] font-medium text-[var(--text-tertiary)] transition-colors hover:text-[var(--brand-primary)]"
              aria-expanded={moreOpen}
              onClick={() => setMoreOpen((open) => !open)}
            >
              同名品牌 {hiddenDuplicateCount}
            </button>
            {moreOpen ? (
              <div className="mt-2 space-y-1.5 rounded-[13px] border border-[var(--border-subtle)] bg-[var(--bg-tertiary)] px-2 py-2">
                {duplicates.map((entity) => {
                  const isSelected = entity.id === selectedBrandId;
                  const name = cleanEntityDisplayText(entity.name, '未命名品牌');
                  const domain = cleanEntityDisplayText(entity.domain, '未设置官网');
                  return (
                    <button
                      key={entity.id}
                      type="button"
                      onClick={() => onSelectBrand(entity.id)}
                      className="grid w-full grid-cols-[28px_minmax(0,1fr)] items-center gap-2 rounded-lg px-2 py-2 text-left transition-colors hover:bg-[var(--bg-secondary)]"
                      style={{
                        background: isSelected ? 'var(--bg-secondary)' : 'transparent',
                      }}
                      aria-label={`切换到同名品牌：${name}`}
                    >
                      <BrandAvatar name={name} domain={entity.domain} size={28} />
                      <span className="min-w-0">
                        <span className="block truncate text-[12px] font-medium text-[var(--text-secondary)]">
                          {name}
                        </span>
                        <span className="block truncate text-[11px] text-[var(--text-tertiary)]">
                          {domain}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            ) : null}
          </div>
        ) : null}

        {showBrandSpaceLink && selectedBrandId ? (
          <button
            type="button"
            onClick={() => router.push(`/brand-space?entity_id=${encodeURIComponent(selectedBrandId)}`)}
            className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-[13px] border text-[13px] font-semibold text-[var(--brand-text)] transition-colors hover:border-[var(--brand-primary)]"
            style={{ borderColor: 'var(--brand-border)', background: 'var(--brand-bg)' }}
          >
            <RiGitBranchLine className="h-4 w-4" />
            进入品牌空间
          </button>
        ) : null}

        <button
          type="button"
          onClick={onAddBrand}
          className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-[13px] border border-dashed text-[13px] font-medium text-[var(--text-secondary)] transition-colors hover:border-[var(--brand-primary)] hover:text-[var(--brand-primary)]"
          style={{ background: 'color-mix(in srgb, var(--bg-secondary) 76%, var(--bg-tertiary) 24%)' }}
        >
          <RiAddLine className="h-4 w-4" />
          新建品牌
        </button>
      </div>

      <BrandManageDialog open={manageOpen} onClose={() => setManageOpen(false)} />
    </aside>
  );
}

export function DashboardMobileBrandSwitcher({
  entities,
  selectedBrandId,
  onSelectBrand,
  onAddBrand,
  showBrandSpaceLink = true,
}: DashboardBrandSidebarProps) {
  const router = useRouter();
  const [manageOpen, setManageOpen] = useState(false);
  const selectedBrand = entities.find((entity) => entity.id === selectedBrandId) || entities[0];
  const selectedName = cleanEntityDisplayText(selectedBrand?.name, '未命名品牌');
  const selectedDomain = cleanEntityDisplayText(selectedBrand?.domain, '未设置官网');
  const { primary, internal, duplicates } = splitDashboardEntities(
    entities,
    selectedBrandId,
  );
  const hiddenCount = duplicates.length;
  void internal;

  return (
    <section className="dashboard-shell rounded-[16px] px-4 py-3 xl:hidden">
      <div className="grid grid-cols-[40px_minmax(0,1fr)_auto] items-center gap-3">
        <BrandAvatar name={selectedName} domain={selectedBrand?.domain} size={40} />
        <label className="min-w-0">
          <span className="block text-[11px] font-medium tracking-[0.12em] text-[var(--text-tertiary)]">
            当前品牌
          </span>
          <select
            value={selectedBrand?.id || ''}
            onChange={(event) => onSelectBrand(event.target.value)}
            className="mt-1 h-10 w-full rounded-lg border bg-[var(--bg-secondary)] px-3 text-[14px] font-semibold text-[var(--text-primary)] outline-none focus:border-[var(--brand-primary)]"
            style={{ borderColor: 'var(--border-subtle)' }}
            aria-label="切换当前品牌"
          >
            {primary.length ? (
              <optgroup label="正式品牌">
                {primary.map((entity) => (
                  <option key={entity.id} value={entity.id}>
                    {cleanEntityDisplayText(entity.name, '未命名品牌')}
                  </option>
                ))}
              </optgroup>
            ) : null}
          </select>
          <span className="mt-1 block truncate text-[12px] text-[var(--text-tertiary)]">
            {hiddenCount ? `${selectedDomain} · 已收起 ${hiddenCount} 个同名品牌` : selectedDomain}
          </span>
        </label>
        <button
          type="button"
          onClick={() => setManageOpen(true)}
          className="inline-flex h-10 w-10 items-center justify-center rounded-lg border text-[var(--text-secondary)] transition-colors hover:border-[var(--brand-primary)] hover:text-[var(--brand-primary)]"
          style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-secondary)' }}
          aria-label="管理品牌"
          title="管理品牌"
        >
          <RiSettings3Line className="h-4 w-4" />
        </button>
      </div>

      {showBrandSpaceLink && selectedBrand?.id ? (
        <button
          type="button"
          onClick={() => router.push(`/brand-space?entity_id=${encodeURIComponent(selectedBrand.id)}`)}
          className="mt-3 inline-flex h-10 w-full items-center justify-center gap-2 rounded-[13px] border text-[13px] font-semibold text-[var(--brand-text)] transition-colors hover:border-[var(--brand-primary)]"
          style={{ borderColor: 'var(--brand-border)', background: 'var(--brand-bg)' }}
        >
          <RiGitBranchLine className="h-4 w-4" />
          进入品牌空间
        </button>
      ) : null}

      {onAddBrand ? (
        <button
          type="button"
          onClick={onAddBrand}
          className="mt-2 inline-flex h-10 w-full items-center justify-center gap-2 rounded-[13px] border border-dashed text-[13px] font-medium text-[var(--text-secondary)] transition-colors hover:border-[var(--brand-primary)] hover:text-[var(--brand-primary)]"
          style={{ background: 'color-mix(in srgb, var(--bg-secondary) 76%, var(--bg-tertiary) 24%)' }}
        >
          <RiAddLine className="h-4 w-4" />
          新建品牌
        </button>
      ) : null}

      <BrandManageDialog open={manageOpen} onClose={() => setManageOpen(false)} />
    </section>
  );
}
