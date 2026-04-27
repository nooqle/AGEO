import Link from 'next/link';

export function HeroSection() {
  return (
    <section className="py-20 bg-[var(--bg-primary)]">
      <div className="max-w-6xl mx-auto px-4 text-center">
        <h1 className="text-5xl font-bold text-[var(--text-primary)] mb-6">
          Specta AI
        </h1>
        <p className="text-xl text-[var(--text-secondary)] mb-8 max-w-2xl mx-auto">
          品牌声量智能分析平台 - 洞察品牌在 AI 平台中的可见性
        </p>
        <Link
          href="/auth"
          className="inline-block rounded-lg bg-[var(--brand-primary)] px-8 py-3 font-medium text-[var(--brand-contrast)] transition-colors hover:bg-[var(--brand-hover)]"
        >
          开始分析
        </Link>
      </div>
    </section>
  );
}
