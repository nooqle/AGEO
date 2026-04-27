'use client';

export function SiteFooter() {
  return (
    <footer className="flex justify-center px-4 py-3 print:hidden md:justify-end md:px-6">
      <div
        className="max-w-full truncate text-[10px] leading-none"
        style={{
          color: 'color-mix(in srgb, var(--text-tertiary) 82%, transparent)',
        }}
      >
        京ICP备2021025648号-11
      </div>
    </footer>
  );
}

export default SiteFooter;
