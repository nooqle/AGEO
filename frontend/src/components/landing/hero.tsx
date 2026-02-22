import Link from 'next/link';

export function HeroSection() {
  return (
    <section className="py-20 bg-[--bg-primary]">
      <div className="max-w-6xl mx-auto px-4 text-center">
        <h1 className="text-5xl font-bold text-[--text-primary] mb-6">
          Specta AI
        </h1>
        <p className="text-xl text-[--text-secondary] mb-8 max-w-2xl mx-auto">
          品牌声量智能分析平台 - 洞察品牌在AI搜索中的可见性
        </p>
        <Link
          href="/dashboard"
          className="inline-block px-8 py-3 bg-[#6366F1] text-white rounded-lg font-medium hover:bg-[#4F46E5] transition-colors"
        >
          开始分析
        </Link>
      </div>
    </section>
  );
}
