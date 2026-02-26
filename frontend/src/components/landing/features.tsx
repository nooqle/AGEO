export function FeaturesSection() {
  const features = [
    {
      title: '品牌档案分析',
      description: '自动收集品牌信息，识别核心产品和市场定位',
    },
    {
      title: '竞品对比',
      description: '识别主要竞品，分析竞争格局和市场机会',
    },
    {
      title: '用户画像生成',
      description: '基于品牌定位生成精准的用户画像和场景',
    },
    {
      title: 'AI可见性监测',
      description: '监测品牌在主流AI平台的可见性和提及率',
    },
  ];

  return (
    <section className="py-20 bg-[--bg-primary]">
      <div className="max-w-6xl mx-auto px-4">
        <h2 className="text-3xl font-bold text-center text-[--text-primary] mb-12">
          核心功能
        </h2>
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
          {features.map((feature, index) => (
            <div key={index} className="p-6 bg-[--bg-secondary] rounded-xl border border-[--border-subtle]">
              <h3 className="text-lg font-semibold text-[--text-primary] mb-2">{feature.title}</h3>
              <p className="text-[--text-secondary] text-sm">{feature.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
