'use client';

import { useState } from 'react';
import { RiAddLine, RiSettings3Line } from '@remixicon/react';
import { BrandAvatar } from './BrandAvatar';
import { BrandManageDialog } from './BrandManageDialog';
import type { Entity } from '@/types/entity';

interface DashboardBrandSidebarProps {
  entities: Entity[];
  selectedBrandId: string | null;
  onSelectBrand: (brandId: string) => void;
  onAddBrand?: () => void;
}

function cleanText(value: string | null | undefined, fallback: string): string {
  const text = (value || '').trim();
  if (!text || /\?{2,}/.test(text)) return fallback;
  return text;
}

export function DashboardBrandSidebar({
  entities,
  selectedBrandId,
  onSelectBrand,
  onAddBrand,
}: DashboardBrandSidebarProps) {
  const [manageOpen, setManageOpen] = useState(false);

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
        {entities.map((entity) => {
          const isSelected = entity.id === selectedBrandId;
          const name = cleanText(entity.name, '未命名品牌');
          const domain = cleanText(entity.domain, '未设置官网');
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
}: DashboardBrandSidebarProps) {
  const [manageOpen, setManageOpen] = useState(false);
  const selectedBrand = entities.find((entity) => entity.id === selectedBrandId) || entities[0];
  const selectedName = cleanText(selectedBrand?.name, '未命名品牌');
  const selectedDomain = cleanText(selectedBrand?.domain, '未设置官网');

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
            {entities.map((entity) => (
              <option key={entity.id} value={entity.id}>
                {cleanText(entity.name, '未命名品牌')}
              </option>
            ))}
          </select>
          <span className="mt-1 block truncate text-[12px] text-[var(--text-tertiary)]">
            {selectedDomain}
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

      <button
        type="button"
        onClick={onAddBrand}
        className="mt-3 inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-lg border border-dashed text-[13px] font-medium text-[var(--text-secondary)] transition-colors hover:border-[var(--brand-primary)] hover:text-[var(--brand-primary)]"
        style={{ background: 'color-mix(in srgb, var(--bg-secondary) 76%, var(--bg-tertiary) 24%)' }}
      >
        <RiAddLine className="h-4 w-4" />
        新建品牌
      </button>

      <BrandManageDialog open={manageOpen} onClose={() => setManageOpen(false)} />
    </section>
  );
}
