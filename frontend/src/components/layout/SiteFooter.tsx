'use client';

export function SiteFooter() {
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-20 flex justify-center px-4 pb-1 print:hidden md:justify-end md:px-6">
      <div
        className="max-w-full truncate text-[10px] leading-none"
        style={{
          color: 'color-mix(in srgb, var(--text-tertiary) 82%, transparent)',
          textShadow: '0 1px 2px rgba(0,0,0,0.22)',
        }}
      >
        京ICP备2021025648号-11
      </div>
    </div>
  );
}

export default SiteFooter;
