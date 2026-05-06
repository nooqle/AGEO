'use client';

import { usePathname } from 'next/navigation';

export function SiteFooter() {
  const pathname = usePathname();
  const isHomePage = pathname === '/';

  return (
    <footer
      className={`flex justify-center px-4 py-3 print:hidden md:justify-end md:px-6 ${
        isHomePage ? 'bg-[#020403]' : ''
      }`}
    >
      <div
        className="max-w-full truncate text-[10px] leading-none"
        style={{
          color: isHomePage
            ? 'rgba(216, 210, 197, 0.62)'
            : 'color-mix(in srgb, var(--text-tertiary) 82%, transparent)',
        }}
      >
        京ICP备2021025648号-11
      </div>
    </footer>
  );
}

export default SiteFooter;
