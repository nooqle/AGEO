'use client';

import Image from 'next/image';
import Link from 'next/link';

interface PublicBrandProps {
  size?: number;
  textSizeClassName?: string;
  className?: string;
}

export function PublicBrand({
  size = 40,
  textSizeClassName = 'text-[34px]',
  className,
}: PublicBrandProps) {
  return (
    <Link
      href="/"
      className={`inline-flex items-center gap-3 text-[#111827] ${className || ''}`}
      aria-label="Specta AI 首页"
    >
      <Image
        src="/logo-light.png"
        alt="Specta AI"
        width={size}
        height={size}
        priority
      />
      <span
        className={`${textSizeClassName} font-semibold tracking-[-0.06em] text-[#111827]`}
      >
        Specta AI
      </span>
    </Link>
  );
}
