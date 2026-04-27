export function HowItWorksSection() {
  return (
    <section className="py-20 bg-[var(--bg-primary)]">
      <div className="max-w-6xl mx-auto px-4">
        <h2 className="text-3xl font-bold text-center text-[var(--text-primary)] mb-12">
          如何使用
        </h2>
        <div className="grid md:grid-cols-3 gap-8">
          <div className="text-center">
            <div className="w-16 h-16 bg-[var(--brand-primary)] rounded-xl flex items-center justify-center mx-auto mb-4">
              <span className="text-2xl font-bold text-white">1</span>
            </div>
            <h3 className="text-xl font-semibold text-[var(--text-primary)] mb-2">输入品牌</h3>
            <p className="text-[var(--text-secondary)]">输入您要分析的品牌名称</p>
          </div>
          <div className="text-center">
            <div className="w-16 h-16 bg-[var(--brand-primary)] rounded-xl flex items-center justify-center mx-auto mb-4">
              <span className="text-2xl font-bold text-white">2</span>
            </div>
            <h3 className="text-xl font-semibold text-[var(--text-primary)] mb-2">AI分析</h3>
            <p className="text-[var(--text-secondary)]">AI自动分析品牌档案、竞品、用户画像</p>
          </div>
          <div className="text-center">
            <div className="w-16 h-16 bg-[var(--brand-primary)] rounded-xl flex items-center justify-center mx-auto mb-4">
              <span className="text-2xl font-bold text-white">3</span>
            </div>
            <h3 className="text-xl font-semibold text-[var(--text-primary)] mb-2">获取报告</h3>
            <p className="text-[var(--text-secondary)]">获取详细的AI可见性分析报告</p>
          </div>
        </div>
      </div>
    </section>
  );
}
