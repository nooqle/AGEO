import Link from 'next/link';

export function CTASection() {
  return (
    <section className="py-20 bg-[var(--bg-primary)]">
      <div className="max-w-4xl mx-auto px-4 text-center">
        <h2 className="text-3xl font-bold text-[var(--text-primary)] mb-4">
          准备好开始了吗？
        </h2>
        <p className="text-[var(--text-secondary)] mb-8">
          立即体验 Specta AI，洞察您的品牌在AI时代的可见性
        </p>
        <Link
          href="/auth"
          className="inline-block rounded-lg bg-[var(--brand-primary)] px-8 py-3 font-medium text-[var(--brand-contrast)] transition-colors hover:bg-[var(--brand-hover)]"
        >
          免费开始
        </Link>
      </div>
    </section>
  );
}
