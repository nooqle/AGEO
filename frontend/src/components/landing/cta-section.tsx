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
          className="inline-block px-8 py-3 bg-[#6366F1] text-white rounded-lg font-medium hover:bg-[#4F46E5] transition-colors"
        >
          免费开始
        </Link>
      </div>
    </section>
  );
}
