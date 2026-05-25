import Image from 'next/image';
import Link from 'next/link';
import Script from 'next/script';
import type { CSSProperties } from 'react';
import {
  RiArrowRightUpLine,
  RiGlobalLine,
  RiSearchEyeLine,
  RiTimerFlashLine,
} from '@remixicon/react';
import { HomeAuthLink, HomeNavActions } from '@/components/home/HomeAuthActions';

const screenshotAssets = {
  dashboard: '/landing/dashboard-real.png',
  settings: '/landing/settings-real.png',
  chat: '/landing/chat-canvas-real.png',
  panoramaQuestions: '/landing/panorama-questions-real.png',
  scenarioTouchpoints: '/landing/scenario-touchpoints-real.png',
  agentReport: '/landing/agent-report-real.png',
} as const;

const capabilityCards = [
  {
    title: '主动监测',
    text: '先建立问题池，观察品牌和竞品在 AI 回答里的位置。',
    icon: <RiSearchEyeLine className="h-5 w-5" />,
    accent: '#46d7bb',
    glow: 'rgba(70,215,187,.34)',
    labels: ['问题池', '回答证据', '来源追溯'],
    variant: 'horizontal',
  },
  {
    title: '持续监测',
    text: '把关键问题设成周期任务，持续记录变化和风险。',
    icon: <RiTimerFlashLine className="h-5 w-5" />,
    accent: '#f0c978',
    glow: 'rgba(240,201,120,.30)',
    labels: ['周期任务', '变化记录', '反馈处理'],
    variant: 'vertical',
  },
  {
    title: '官网评估',
    text: '检查官网是否被引用、是否可读、是否能支撑品牌叙事。',
    icon: <RiGlobalLine className="h-5 w-5" />,
    accent: '#8cc8ff',
    glow: 'rgba(140,200,255,.28)',
    labels: ['引用占比', '内容缺口', '优化建议'],
    variant: 'diagonal',
  },
] as const;

const reelSlides = [
  {
    kicker: '主动监测',
    title: 'AI品牌情报系统',
    image: screenshotAssets.panoramaQuestions,
    tone: 'blue',
  },
  {
    kicker: '持续监测',
    title: '持续追踪',
    image: screenshotAssets.settings,
    tone: 'amber',
  },
  {
    kicker: 'Chat + Canvas',
    title: 'AI品牌情报系统',
    image: screenshotAssets.agentReport,
    tone: 'teal',
  },
] as const;

const faqs = [
  {
    question: 'Specta 主要解决什么问题？',
    answer: '看品牌在 AI 答案里的表现，并把问题、回答、引用、官网观测和人的反馈沉淀成可复核的品牌情报。',
  },
  {
    question: '会覆盖哪些平台？',
    answer: '主动监测覆盖豆包、元宝、DeepSeek、Kimi；持续监测优先覆盖豆包、元宝、Kimi，并按周期记录变化。',
  },
  {
    question: '监测采集模式有哪些？',
    answer:
      '快速采集可以在短时间内进行答案监测，省时省费用。完整采集会完全模拟用户输入进行答案监测，时间较长，费用较高。推荐平时监测使用快速采集模式，每个月做一次完整采集，把品牌监控放在不同维度里分析。',
  },
  {
    question: '官网评估为什么重要？',
    answer: '官网是品牌最应该掌握的信源。内容越清晰，越容易被 AI 回答引用、理解和正确转述。',
  },
] as const;

function ApertureLogo({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`aperture-logo ${compact ? 'aperture-logo--compact' : ''}`}>
      <span className="aperture-orbit aperture-orbit--a" />
      <span className="aperture-orbit aperture-orbit--b" />
      <span className="aperture-scan" />
      <Image
        src="/logo-light.png"
        alt="Specta AI"
        width={compact ? 34 : 82}
        height={compact ? 34 : 82}
        className="relative z-10 invert"
        priority
      />
    </div>
  );
}

function PromptBar() {
  return (
    <div className="prompt-bar">
      <span className="prompt-text">问 Specta：为什么官网没有被引用？</span>
      <Link href="/auth?mode=apply" className="prompt-button" aria-label="申请体验">
        <RiArrowRightUpLine className="h-5 w-5" />
      </Link>
    </div>
  );
}

function HeroSignal() {
  return (
    <section className="hero-section">
      <div className="hero-grid hero-grid--top" />
      <div className="hero-grid hero-grid--bottom" />
      <span className="space-ring space-ring--one" />
      <span className="space-ring space-ring--two" />
      <span className="space-dot space-dot--one" />
      <span className="space-dot space-dot--two" />

      <div className="hero-mark" data-heat-target aria-hidden="true">
        <span className="hero-word hero-word--ghost">Specta</span>
        <span className="hero-word hero-word--main">Specta</span>
      </div>

      <div className="hero-copy">
        <h1>AI品牌情报系统</h1>
        <p>问题、回答、引用、官网和人的反馈，沉淀成同一个品牌情报视图。</p>
        <PromptBar />
        <div className="hero-actions">
          <Link href="/auth?mode=apply">申请体验</Link>
          <a href="#product-reel">查看能力</a>
        </div>
      </div>
    </section>
  );
}

function CapabilitySection() {
  return (
    <section className="section-shell" id="capabilities">
      <div className="section-heading">
        <h2>三类能力沉淀品牌情报</h2>
        <p>把品牌位置、证据来源、官网表现和持续变化放在一套工作台里。</p>
      </div>
      <div className="capability-grid">
        {capabilityCards.map((card) => (
          <article
            key={card.title}
            className={`capability-card capability-card--${card.variant}`}
            style={{ '--accent': card.accent, '--glow': card.glow } as CSSProperties}
          >
            <div className="capability-visual" aria-hidden="true">
              <span className="capability-planet" />
              <span className="capability-line capability-line--a" />
              <span className="capability-line capability-line--b" />
            </div>
            <div className="capability-meta">
              <span>{card.icon}</span>
              <h3>{card.title}</h3>
              <p>{card.text}</p>
            </div>
            <div className="capability-labels">
              {card.labels.map((label) => (
                <span key={label}>{label}</span>
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function FramedShot({
  src,
  alt,
  caption,
  className = '',
  priority = false,
}: {
  src: string;
  alt: string;
  caption: string;
  className?: string;
  priority?: boolean;
}) {
  return (
    <div className={`framed-shot ${className}`}>
      <div className="framed-shot-caption">{caption}</div>
      <div className="framed-shot-image">
        <Image
          src={src}
          alt={alt}
          width={1440}
          height={980}
          priority={priority}
          className="h-full w-full object-cover"
        />
      </div>
    </div>
  );
}

function SlideVisual({ slide }: { slide: (typeof reelSlides)[number] }) {
  if (slide.tone === 'teal') {
    return (
      <div className="visual-stage visual-stage--single">
        <FramedShot
          src={slide.image}
          alt="Specta Chat 与 Canvas 真实产品界面"
          caption="围绕某条情报继续追问原因、证据和下一步。"
          className="framed-shot--wide framed-shot--chat"
          priority
        />
      </div>
    );
  }

  if (slide.tone === 'blue') {
    return (
      <div className="visual-stage visual-stage--analysis">
        <FramedShot
          src={slide.image}
          alt="Specta 全景分析真实产品界面"
          caption="主动监测 - 建立问题池并观察品牌位置"
          className="framed-shot--panorama"
          priority
        />
        <FramedShot
          src={screenshotAssets.scenarioTouchpoints}
          alt="Specta 场景分析与用户画像触点真实产品界面"
          caption="场景分析 - 在具体人群痛点里追溯证据"
          className="framed-shot--scenario"
        />
      </div>
    );
  }

  return (
    <div className="visual-stage visual-stage--single">
      <FramedShot
        src={slide.image}
        alt="Specta 持续监测设置真实产品界面"
        caption="定时自动化追踪 - 品牌优化可以透过时间看到"
        className="framed-shot--wide framed-shot--settings"
      />
    </div>
  );
}

function ProductReelSection() {
  return (
    <section className="product-reel-section" id="product-reel">
      <div className="section-heading section-heading--center">
        <h2>AI品牌情报系统</h2>
        <p>用户提问，Specta 执行监测。结果以证据、报告和看板持续沉淀。</p>
      </div>
      <div className="reel-window">
        <div className="reel-rail" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
        <div className="reel-track">
          {reelSlides.map((slide) => (
            <article key={slide.title} className="reel-slide">
              <div className="reel-copy">
                <h3>{slide.title}</h3>
              </div>
              <SlideVisual slide={slide} />
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function BrandPortalSection() {
  return (
    <section className="brand-portal">
      <div className="portal-grid portal-grid--ceiling" />
      <div className="portal-grid portal-grid--floor" />
      <span className="space-ring space-ring--three" />
      <span className="space-dot space-dot--three" />
      <div className="portal-logo">
        <ApertureLogo />
      </div>
      <h2>Specta AI</h2>
      <p className="portal-heatline" data-heat-target>
        AI品牌情报系统
      </p>
      <div className="portal-actions">
        <Link href="/auth?mode=apply">申请体验</Link>
        <HomeAuthLink />
      </div>
      <div className="portal-prompt">
        <span>问 Specta</span>
        <b>哪些证据支撑这个判断？</b>
        <RiArrowRightUpLine className="h-5 w-5" />
      </div>
    </section>
  );
}

function FaqSection() {
  return (
    <section className="faq-section" id="faq">
      <div className="section-heading section-heading--center">
        <h2>常见问题</h2>
      </div>
      <div className="faq-list">
        {faqs.map((item, index) => (
          <details key={item.question} className={index !== faqs.length - 1 ? 'with-border' : ''}>
            <summary>
              <span>{item.question}</span>
              <span>+</span>
            </summary>
            <p>{item.answer}</p>
          </details>
        ))}
      </div>
    </section>
  );
}

function HomePage() {
  return (
    <main className="specta-home min-h-screen overflow-hidden bg-[#020403] text-[#f1eee6]">
      <style>{`
        @keyframes aperture-sweep {
          0% { transform: translateX(-50%) rotate(0deg); opacity: .22; }
          50% { opacity: .7; }
          100% { transform: translateX(-50%) rotate(360deg); opacity: .22; }
        }
        @keyframes aperture-orbit {
          0% { transform: rotateX(64deg) rotateZ(0deg); }
          100% { transform: rotateX(64deg) rotateZ(360deg); }
        }
        @keyframes raster-flow {
          0% { background-position: 0 0, 0 0, 0 0, 0 0, 0 0, 0 0, 0 0; }
          100% { background-position: 0 30px, 22px 0, -28px 18px, 40px -14px, -44px 12px, 0 0, 260px 0; }
        }
        @keyframes dot-drift {
          0%, 100% { transform: translate3d(0,0,0); opacity: .35; }
          50% { transform: translate3d(-18px,12px,0); opacity: .9; }
        }
        @keyframes reel-shift {
          0%, 25% { transform: translate3d(0,0,0); }
          34%, 58% { transform: translate3d(0,-33.333%,0); }
          67%, 91% { transform: translate3d(0,-66.666%,0); }
          100% { transform: translate3d(0,0,0); }
        }
        @keyframes portal-float {
          0%, 100% { transform: translate3d(0,0,0); }
          50% { transform: translate3d(0,-12px,0); }
        }
        .specta-home {
          color-scheme: dark;
          --paper: #f1eee6;
          --muted: rgba(216, 210, 197, .48);
          --line: rgba(241, 238, 230, .13);
          --panel: rgba(24, 24, 22, .78);
          --teal: #46d7bb;
          --ease: cubic-bezier(.22,1,.36,1);
        }
        .aperture-logo {
          position: relative;
          display: flex;
          height: 148px;
          width: 148px;
          align-items: center;
          justify-content: center;
          border: 1px solid rgba(241,238,230,.13);
          border-radius: 34px;
          background: rgba(241,238,230,.035);
          box-shadow: 0 0 80px rgba(70,215,187,.12);
        }
        .aperture-logo--compact {
          height: 48px;
          width: 48px;
          border-radius: 18px;
        }
        .aperture-orbit {
          position: absolute;
          inset: -46%;
          border: 1px solid rgba(241,238,230,.13);
          border-radius: 999px;
          animation: aperture-orbit 16s linear infinite;
        }
        .aperture-orbit--b {
          inset: -22%;
          opacity: .52;
          animation-duration: 11s;
          animation-direction: reverse;
        }
        .aperture-scan {
          position: absolute;
          left: 50%;
          top: -42%;
          height: 184%;
          width: 1px;
          background: linear-gradient(to bottom, transparent, rgba(241,238,230,.68), transparent);
          animation: aperture-sweep 8s linear infinite;
        }
        .site-header {
          position: fixed;
          left: 0;
          right: 0;
          top: 0;
          z-index: 50;
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 28px clamp(24px, 5vw, 92px);
          background: linear-gradient(to bottom, rgba(2,4,3,.9), rgba(2,4,3,.42), transparent);
        }
        .site-brand,
        .nav-actions,
        .site-nav {
          display: flex;
          align-items: center;
        }
        .site-brand {
          gap: 14px;
          color: var(--paper);
          font-size: 28px;
          font-weight: 700;
        }
        .site-nav {
          gap: 32px;
          font-size: 14px;
          font-weight: 650;
          color: rgba(216,210,197,.44);
        }
        .site-nav a,
        .nav-actions a,
        .hero-actions a,
        .portal-actions a,
        .reel-copy a {
          transition: color .28s var(--ease), border-color .28s var(--ease), background .28s var(--ease), transform .28s var(--ease);
        }
        .site-nav a:hover {
          color: var(--paper);
        }
        .nav-actions {
          gap: 12px;
        }
        .nav-actions a {
          min-height: 46px;
          border-radius: 999px;
          padding: 13px 22px;
          font-size: 14px;
          font-weight: 700;
        }
        .nav-actions a:first-child {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          border: 1px solid rgba(241,238,230,.12);
          color: rgba(216,210,197,.58);
        }
        .nav-actions a:last-child {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          background: var(--paper);
          color: #080908;
        }
        .nav-actions a:last-child:hover,
        .hero-actions a:first-child:hover,
        .portal-actions a:first-child:hover {
          background: color-mix(in srgb, var(--paper) 92%, var(--teal));
          color: #080908;
        }
        .hero-section {
          position: relative;
          min-height: 100vh;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 150px 24px 96px;
          isolation: isolate;
        }
        .hero-section::before {
          content: '';
          position: absolute;
          inset: 0;
          background:
            radial-gradient(circle at 50% 22%, rgba(70,215,187,.13), transparent 32%),
            linear-gradient(to bottom, rgba(2,4,3,.1), #020403 88%);
          z-index: -3;
        }
        .hero-grid,
        .portal-grid {
          position: absolute;
          left: 50%;
          width: min(76vw, 1120px);
          height: 300px;
          transform: translateX(-50%) perspective(760px) rotateX(64deg);
          border: 1px solid rgba(241,238,230,.13);
          border-radius: 30px;
          background:
            linear-gradient(to bottom, rgba(241,238,230,.15), transparent 1px),
            linear-gradient(102deg, transparent 0 13%, rgba(241,238,230,.11) 13.2% 13.35%, transparent 13.55% 100%),
            linear-gradient(78deg, transparent 0 13%, rgba(241,238,230,.11) 13.2% 13.35%, transparent 13.55% 100%);
          background-size: 100% 82px, 160px 100%, 160px 100%;
          opacity: .28;
          z-index: -2;
        }
        .hero-grid--top { top: 86px; mask-image: linear-gradient(to bottom, black, transparent); }
        .hero-grid--bottom { bottom: 16px; transform: translateX(-50%) perspective(760px) rotateX(64deg) rotate(180deg); mask-image: linear-gradient(to top, black, transparent); }
        .space-ring {
          position: absolute;
          border: 2px solid rgba(241,238,230,.36);
          border-radius: 999px;
          box-shadow: inset 0 0 24px rgba(241,238,230,.08), 0 0 32px rgba(70,215,187,.12);
        }
        .space-ring--one { right: 7%; top: 12%; width: 42px; height: 42px; }
        .space-ring--two { right: 18%; bottom: 19%; width: 64px; height: 64px; opacity: .45; }
        .space-ring--three { right: 8%; top: 20%; width: 48px; height: 48px; }
        .space-dot {
          position: absolute;
          width: 6px;
          height: 6px;
          border-radius: 999px;
          background: var(--paper);
          box-shadow: 0 0 26px rgba(241,238,230,.5);
          animation: dot-drift 6s ease-in-out infinite;
        }
        .space-dot--one { right: 5%; top: 8%; }
        .space-dot--two { left: 17%; bottom: 16%; animation-delay: -2s; }
        .space-dot--three { right: 15%; bottom: 23%; animation-delay: -3s; }
        .hero-mark {
          position: absolute;
          left: 50%;
          top: 22%;
          width: min(1180px, 95vw);
          height: 230px;
          transform: translateX(-50%);
          z-index: -1;
          cursor: default;
          pointer-events: auto;
          --heat-x: 50%;
          --heat-y: 50%;
        }
        .hero-mark::after {
          content: '';
          position: absolute;
          inset: 8% 6%;
          border-radius: 999px;
          background:
            radial-gradient(
              520px circle at var(--heat-x) var(--heat-y),
              rgba(255,255,255,.72) 0%,
              rgba(255,235,59,.64) 5%,
              rgba(255,61,0,.58) 15%,
              rgba(233,30,99,.4) 25%,
              rgba(33,150,243,.34) 45%,
              rgba(0,0,128,.2) 65%,
              transparent 80%
            );
          mix-blend-mode: screen;
          filter: blur(42px);
          opacity: 0;
          transform: scale(.92);
          transition: opacity .45s var(--ease), transform .45s var(--ease);
          z-index: 0;
        }
        .hero-mark:hover::after {
          opacity: .72;
          transform: scale(1);
        }
        .hero-word {
          position: absolute;
          inset: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: clamp(7rem, 18vw, 19rem);
          font-weight: 760;
          line-height: 1;
          z-index: 1;
        }
        .hero-word--ghost {
          color: rgba(241,238,230,.11);
          filter: blur(4px);
          transform: scaleX(1.08);
        }
        .hero-word--main {
          color: transparent;
          background:
            repeating-linear-gradient(0deg, rgba(241,238,230,.18) 0 2px, rgba(70,215,187,.035) 2px 7px),
            linear-gradient(90deg, transparent 0%, rgba(241,238,230,.08) 22%, rgba(241,238,230,.32) 52%, rgba(70,215,187,.16) 72%, transparent 100%);
          -webkit-background-clip: text;
          background-clip: text;
          text-shadow: 10px 0 30px rgba(70,215,187,.04), -8px 0 26px rgba(240,201,120,.04);
          opacity: .56;
          animation: raster-flow 7s linear infinite;
          mask-image: linear-gradient(90deg, transparent 0%, black 14%, black 84%, transparent 100%);
          transition: opacity .45s var(--ease), filter .45s var(--ease), text-shadow .45s var(--ease);
        }
        .hero-mark:hover .hero-word--main {
          background:
            repeating-linear-gradient(0deg, rgba(255,255,255,.42) 0 2px, rgba(0,0,0,.08) 2px 7px),
            radial-gradient(
              500px circle at var(--heat-x) var(--heat-y),
              rgba(255,255,255,.95) 0%,
              rgba(255,235,59,.86) 5%,
              rgba(255,61,0,.78) 15%,
              rgba(233,30,99,.56) 25%,
              rgba(33,150,243,.44) 45%,
              rgba(0,0,128,.28) 65%,
              transparent 80%
            ),
            linear-gradient(90deg, #06113c 0%, #0b2d87 45%, #091c4e 100%);
          -webkit-background-clip: text;
          background-clip: text;
          filter: saturate(1.06) brightness(1.04) contrast(1.08);
          opacity: .94;
          text-shadow: 0 0 42px rgba(28,206,232,.16), 0 0 82px rgba(255,102,26,.15);
        }
        .hero-copy {
          width: min(940px, 100%);
          text-align: center;
          transform: translateY(122px);
        }
        .hero-copy h1 {
          font-size: clamp(2.4rem, 3.9vw, 4.6rem);
          font-weight: 760;
          line-height: 1.05;
          color: var(--paper);
          white-space: nowrap;
        }
        .hero-copy p {
          margin: 24px auto 34px;
          max-width: 680px;
          color: rgba(216,210,197,.5);
          font-size: 18px;
          line-height: 1.9;
        }
        .prompt-bar {
          margin: 0 auto;
          display: flex;
          width: min(620px, 92vw);
          align-items: center;
          gap: 12px;
          border: 1px solid rgba(241,238,230,.12);
          border-radius: 30px;
          background: rgba(25,25,24,.86);
          padding: 12px;
          box-shadow: 0 26px 70px rgba(0,0,0,.45), inset 0 1px 0 rgba(241,238,230,.06);
          backdrop-filter: blur(16px);
        }
        .prompt-text {
          flex: 1;
          border-radius: 22px;
          background: rgba(241,238,230,.035);
          padding: 18px 22px;
          text-align: left;
          color: rgba(216,210,197,.45);
          font-size: 15px;
          font-weight: 650;
        }
        .prompt-button {
          display: flex;
          height: 56px;
          width: 56px;
          flex: 0 0 auto;
          align-items: center;
          justify-content: center;
          border-radius: 999px;
          background: rgba(241,238,230,.16);
          color: var(--paper);
        }
        .hero-actions,
        .portal-actions {
          margin-top: 30px;
          display: flex;
          justify-content: center;
          gap: 14px;
        }
        .hero-actions a,
        .portal-actions a,
        .reel-copy a {
          display: inline-flex;
          min-height: 46px;
          align-items: center;
          justify-content: center;
          border: 1px solid rgba(241,238,230,.22);
          border-radius: 999px;
          padding: 0 24px;
          color: rgba(241,238,230,.72);
          font-size: 14px;
          font-weight: 700;
        }
        .hero-actions a:first-child,
        .portal-actions a:first-child {
          background: var(--paper);
          color: #080908;
        }
        .hero-actions a:hover,
        .portal-actions a:hover,
        .reel-copy a:hover {
          transform: translateY(-2px);
          border-color: rgba(241,238,230,.42);
          color: var(--paper);
        }
        .hero-actions a:first-child:hover,
        .portal-actions a:first-child:hover {
          color: #080908;
        }
        .section-shell,
        .product-reel-section,
        .faq-section {
          scroll-margin-top: 96px;
          padding: 120px clamp(24px, 7vw, 140px);
        }
        .section-heading {
          display: flex;
          align-items: end;
          justify-content: space-between;
          gap: 28px;
          margin: 0 auto 58px;
          max-width: 1320px;
        }
        .section-heading--center {
          display: block;
          text-align: center;
        }
        .section-heading h2 {
          max-width: 720px;
          color: var(--paper);
          font-size: clamp(2.2rem, 4vw, 4.1rem);
          font-weight: 760;
          line-height: 1.08;
        }
        .section-heading p {
          max-width: 680px;
          color: rgba(216,210,197,.45);
          font-size: 18px;
          line-height: 1.85;
        }
        .section-heading--center p {
          margin: 18px auto 0;
        }
        .capability-grid {
          display: grid;
          max-width: 1320px;
          margin: 0 auto;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 26px;
        }
        .capability-card {
          position: relative;
          min-height: 360px;
          overflow: hidden;
          border: 1px solid rgba(241,238,230,.13);
          border-radius: 22px;
          background: linear-gradient(180deg, rgba(18,18,17,.96), rgba(8,9,8,.96));
          padding: 30px;
          transition: transform .45s var(--ease), border-color .45s var(--ease), box-shadow .45s var(--ease);
        }
        .capability-card::before {
          content: '';
          position: absolute;
          inset: 0;
          background: radial-gradient(circle at 42% 36%, var(--glow), transparent 42%);
          opacity: 0;
          transition: opacity .45s var(--ease);
        }
        .capability-card:hover {
          transform: translateY(-8px);
          border-color: color-mix(in srgb, var(--accent) 44%, transparent);
          box-shadow: 0 34px 120px rgba(0,0,0,.48), 0 0 90px var(--glow);
        }
        .capability-card:hover::before {
          opacity: 1;
        }
        .capability-visual {
          position: absolute;
          inset: 0;
          opacity: .78;
        }
        .capability-planet {
          position: absolute;
          left: 50%;
          top: 38%;
          width: 150px;
          height: 150px;
          transform: translate(-50%, -50%);
          border-radius: 50%;
          background:
            radial-gradient(circle at 42% 36%, var(--accent), transparent 18%),
            radial-gradient(circle at 58% 58%, rgba(241,238,230,.28), transparent 36%),
            rgba(241,238,230,.06);
          filter: blur(.2px);
        }
        .capability-line {
          position: absolute;
          left: 16%;
          right: 16%;
          top: 38%;
          height: 1px;
          background: linear-gradient(90deg, transparent, rgba(241,238,230,.22), transparent);
        }
        .capability-line--a { transform: rotate(18deg); }
        .capability-line--b { transform: rotate(-18deg); }
        .capability-card--horizontal .capability-line--a { transform: rotate(7deg); }
        .capability-card--horizontal .capability-line--b { transform: rotate(-7deg); }
        .capability-card--vertical .capability-planet {
          top: 36%;
          width: 128px;
          height: 178px;
        }
        .capability-card--vertical .capability-line {
          left: 50%;
          right: auto;
          top: 18%;
          width: 1px;
          height: 220px;
          background: linear-gradient(to bottom, transparent, rgba(241,238,230,.24), transparent);
          transform-origin: center;
        }
        .capability-card--vertical .capability-line--a { transform: translateX(-50%) rotate(0deg); }
        .capability-card--vertical .capability-line--b { transform: translateX(-50%) rotate(82deg); }
        .capability-card--diagonal .capability-planet {
          left: 58%;
          top: 34%;
          width: 136px;
          height: 136px;
        }
        .capability-card--diagonal .capability-line--a { transform: rotate(23deg); }
        .capability-card--diagonal .capability-line--b { transform: rotate(-31deg); }
        .capability-meta {
          position: relative;
          z-index: 1;
          margin-top: 190px;
        }
        .capability-meta > span {
          display: inline-flex;
          width: 42px;
          height: 42px;
          align-items: center;
          justify-content: center;
          border: 1px solid rgba(241,238,230,.14);
          border-radius: 999px;
          color: var(--accent);
        }
        .capability-meta h3 {
          margin-top: 18px;
          font-size: 28px;
          font-weight: 760;
          transition: color .35s var(--ease), text-shadow .35s var(--ease);
        }
        .capability-meta p {
          margin-top: 12px;
          color: rgba(216,210,197,.48);
          line-height: 1.8;
          transition: color .35s var(--ease);
        }
        .capability-card:hover .capability-meta h3 {
          color: var(--accent);
          text-shadow: 0 0 30px var(--glow);
        }
        .capability-card:hover .capability-meta p {
          color: color-mix(in srgb, var(--accent) 36%, rgba(216,210,197,.6));
        }
        .capability-labels {
          position: relative;
          z-index: 1;
          margin-top: 22px;
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }
        .capability-labels span {
          border: 1px solid transparent;
          border-radius: 999px;
          background: rgba(241,238,230,.07);
          padding: 8px 11px;
          color: rgba(241,238,230,.72);
          font-size: 12px;
          font-weight: 700;
          transition: background .35s var(--ease), border-color .35s var(--ease), color .35s var(--ease), transform .35s var(--ease);
        }
        .capability-card:hover .capability-labels span {
          border-color: color-mix(in srgb, var(--accent) 38%, transparent);
          background: color-mix(in srgb, var(--accent) 18%, rgba(241,238,230,.06));
          color: color-mix(in srgb, var(--accent) 76%, var(--paper));
          transform: translateY(-2px);
        }
        .product-reel-section {
          min-height: 100vh;
        }
        .reel-window {
          position: relative;
          margin: 60px auto 0;
          height: 690px;
          max-width: 1420px;
          overflow: hidden;
        }
        .reel-rail {
          position: absolute;
          left: 3%;
          top: 230px;
          z-index: 3;
          display: flex;
          height: 138px;
          width: 12px;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 12px;
        }
        .reel-rail span {
          position: relative;
          z-index: 1;
          width: 7px;
          height: 28px;
          border-radius: 999px;
          background: rgba(241,238,230,.22);
        }
        .reel-rail span:first-child {
          height: 44px;
          background: rgba(241,238,230,.62);
          box-shadow: 0 0 18px rgba(241,238,230,.16);
        }
        .reel-track {
          height: 300%;
          animation: reel-shift 20s var(--ease) infinite;
        }
        .reel-slide {
          display: grid;
          height: 690px;
          grid-template-columns: .38fr .62fr;
          align-items: center;
          gap: 56px;
          padding-left: 86px;
        }
        .reel-copy {
          max-width: 560px;
        }
        .reel-kicker {
          color: rgba(216,210,197,.42);
          font-size: 14px;
          font-weight: 750;
        }
        .reel-copy h3 {
          color: var(--paper);
          font-size: clamp(3rem, 4.4vw, 5rem);
          font-weight: 760;
          line-height: 1.04;
          white-space: nowrap;
        }
        .reel-copy p {
          margin-top: 26px;
          color: rgba(216,210,197,.48);
          font-size: 20px;
          line-height: 1.8;
        }
        .reel-copy a {
          margin-top: 56px;
        }
        .visual-stage {
          position: relative;
          height: 560px;
          perspective: 1300px;
          transform-style: preserve-3d;
        }
        .visual-stage--analysis {
          display: block;
        }
        .visual-stage--single {
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .framed-shot {
          position: relative;
          overflow: hidden;
          border: 1px solid rgba(241,238,230,.12);
          border-radius: 24px;
          background:
            linear-gradient(180deg, rgba(32,32,31,.88), rgba(10,12,10,.92)),
            radial-gradient(circle at 18% 0%, rgba(70,215,187,.12), transparent 32%);
          padding: 58px 0 0;
          box-shadow: 0 48px 140px rgba(0,0,0,.58), inset 0 1px 0 rgba(241,238,230,.08);
          transition: opacity .45s var(--ease), filter .45s var(--ease), transform .45s var(--ease);
        }
        .framed-shot::before {
          content: '';
          position: absolute;
          inset: 0;
          border-radius: inherit;
          background:
            linear-gradient(135deg, rgba(241,238,230,.08), transparent 26%, rgba(0,0,0,.24)),
            radial-gradient(circle at 22% 0%, rgba(70,215,187,.13), transparent 32%);
          opacity: .58;
          pointer-events: none;
        }
        .framed-shot-caption {
          position: absolute;
          left: 0;
          right: 0;
          top: 0;
          z-index: 2;
          display: flex;
          min-height: 58px;
          align-items: center;
          gap: 12px;
          border-bottom: 1px solid rgba(241,238,230,.08);
          background: rgba(31,31,30,.88);
          padding: 0 22px;
          color: rgba(241,238,230,.82);
          font-size: 15px;
          font-weight: 760;
          letter-spacing: 0;
          backdrop-filter: blur(14px);
        }
        .framed-shot-caption::before {
          content: '';
          width: 18px;
          height: 18px;
          flex: 0 0 auto;
          border: 2px solid currentColor;
          border-radius: 6px;
          opacity: .8;
          box-shadow: inset 0 -5px 0 rgba(241,238,230,.16);
        }
        .framed-shot-image {
          position: relative;
          z-index: 1;
          height: 100%;
          overflow: hidden;
          border: 0;
          border-radius: 0 0 24px 24px;
          background: #030604;
        }
        .framed-shot-image img {
          object-fit: contain !important;
          object-position: center;
          opacity: .82;
          filter: brightness(1.02) contrast(1.05) saturate(.92);
          transition: opacity .45s var(--ease), filter .45s var(--ease);
        }
        .framed-shot-image::after {
          content: '';
          position: absolute;
          inset: 0;
          background: linear-gradient(135deg, rgba(241,238,230,.08), transparent 30%, rgba(0,0,0,.2));
          pointer-events: none;
        }
        .framed-shot--panorama,
        .framed-shot--scenario {
          position: absolute;
          height: 390px;
          width: min(760px, 88%);
        }
        .framed-shot--panorama {
          right: 1%;
          top: 0;
          opacity: .62;
          transform: translate3d(38px,-20px,-130px) rotateY(-13deg) rotateZ(3deg);
        }
        .framed-shot--scenario {
          right: 12%;
          top: 172px;
          opacity: .9;
          transform: translate3d(-48px,0,90px) rotateY(-5deg) rotateZ(-2.5deg);
        }
        .framed-shot--scenario::before {
          background: linear-gradient(135deg, rgba(240,201,120,.18), transparent 34%, rgba(70,215,187,.12));
        }
        .framed-shot--scenario .framed-shot-caption {
          color: rgba(240,201,120,.9);
        }
        .framed-shot--wide {
          position: absolute;
          right: 7%;
          top: 62px;
          width: min(880px, 92%);
          height: 440px;
          transform: translate3d(0,0,90px) rotateY(-8deg) rotateZ(1.2deg);
        }
        .framed-shot--chat {
          width: min(960px, 100%);
          transform: translate3d(0,0,90px) rotateY(-7deg) rotateZ(-1.4deg);
        }
        .framed-shot--settings::before {
          background: linear-gradient(135deg, rgba(240,201,120,.18), transparent 32%, rgba(70,215,187,.12));
        }
        .framed-shot:hover {
          opacity: .95;
          filter: brightness(1.04);
        }
        .framed-shot:hover .framed-shot-image img {
          opacity: .94;
          filter: brightness(1.08) contrast(1.08) saturate(.98);
        }
        .brand-portal {
          position: relative;
          min-height: 940px;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          overflow: hidden;
          padding: 140px 24px;
          text-align: center;
        }
        .portal-grid {
          width: min(70vw, 1040px);
          height: 280px;
        }
        .portal-grid--ceiling {
          top: 120px;
          mask-image: linear-gradient(to bottom, black, transparent);
        }
        .portal-grid--floor {
          bottom: 70px;
          transform: translateX(-50%) perspective(760px) rotateX(64deg) rotate(180deg);
          mask-image: linear-gradient(to top, black, transparent);
        }
        .portal-logo {
          position: relative;
          z-index: 2;
          animation: portal-float 6s var(--ease) infinite;
        }
        .portal-logo .aperture-logo {
          width: 132px;
          height: 132px;
          border-radius: 34px;
        }
        .brand-portal h2 {
          margin-top: 42px;
          font-size: clamp(2.8rem, 5vw, 5.4rem);
          font-weight: 760;
        }
        .brand-portal p {
          margin-top: 20px;
          max-width: 680px;
          --heat-x: 50%;
          --heat-y: 50%;
          color: rgba(216,210,197,.48);
          -webkit-text-fill-color: currentColor;
          filter: none;
          font-size: 20px;
          line-height: 1.8;
          white-space: nowrap;
          cursor: default;
          transition: color .35s var(--ease), filter .35s var(--ease), opacity .35s var(--ease);
        }
        .brand-portal p:hover {
          color: transparent;
          background:
            radial-gradient(
              340px circle at var(--heat-x) var(--heat-y),
              rgba(255,255,255,.96) 0%,
              rgba(255,235,59,.88) 6%,
              rgba(255,61,0,.76) 17%,
              rgba(233,30,99,.48) 28%,
              rgba(33,150,243,.42) 48%,
              rgba(0,0,128,.24) 66%,
              transparent 82%
            ),
            linear-gradient(90deg, rgba(216,210,197,.46) 0%, rgba(42,163,241,.42) 44%, rgba(216,210,197,.38) 100%);
          -webkit-background-clip: text;
          background-clip: text;
          -webkit-text-fill-color: transparent;
          filter: drop-shadow(0 0 26px rgba(255,104,28,.18));
        }
        .portal-prompt {
          margin-top: 70px;
          display: grid;
          width: min(560px, 92vw);
          grid-template-columns: auto 1fr auto;
          align-items: center;
          gap: 16px;
          border: 1px solid rgba(241,238,230,.13);
          border-radius: 999px;
          background: rgba(28,28,26,.88);
          padding: 17px 22px;
          color: rgba(216,210,197,.52);
          box-shadow: 0 34px 100px rgba(0,0,0,.45);
        }
        .portal-prompt b {
          color: rgba(241,238,230,.72);
          font-size: 15px;
        }
        .faq-section {
          padding-top: 40px;
        }
        .faq-list {
          max-width: 960px;
          margin: 0 auto;
          border: 1px solid rgba(241,238,230,.1);
          border-radius: 28px;
          background: rgba(22,22,20,.8);
        }
        .faq-list details {
          padding: 24px 28px;
        }
        .faq-list details.with-border {
          border-bottom: 1px solid rgba(241,238,230,.08);
        }
        .faq-list summary {
          display: grid;
          cursor: pointer;
          grid-template-columns: 1fr 24px;
          align-items: center;
          gap: 20px;
          list-style: none;
          color: var(--paper);
          font-size: 18px;
          font-weight: 760;
        }
        .faq-list summary::-webkit-details-marker {
          display: none;
        }
        .faq-list summary span:last-child {
          color: rgba(216,210,197,.42);
          transition: transform .25s var(--ease);
        }
        .faq-list details[open] summary span:last-child {
          transform: rotate(45deg);
        }
        .faq-list p {
          margin-top: 18px;
          max-width: 780px;
          color: rgba(216,210,197,.52);
          line-height: 1.9;
        }
        .site-footer {
          display: flex;
          align-items: end;
          justify-content: space-between;
          gap: 36px;
          border-top: 1px solid rgba(241,238,230,.08);
          margin: 40px clamp(24px, 7vw, 140px) 0;
          padding: 42px 0;
          color: rgba(216,210,197,.42);
        }
        .site-footer p {
          margin-top: 12px;
          max-width: 520px;
          line-height: 1.8;
        }
        .footer-links {
          display: flex;
          gap: 32px;
          font-size: 14px;
        }
        .footer-links a:hover {
          color: var(--paper);
        }
        @media (max-width: 1100px) {
          .site-nav { display: none; }
          .capability-grid { grid-template-columns: 1fr; }
          .reel-window {
            height: auto;
            overflow: visible;
          }
          .reel-track {
            height: auto;
            animation: none;
          }
          .reel-slide {
            height: auto;
            grid-template-columns: 1fr;
            padding: 40px 0 80px;
          }
          .reel-rail { display: none; }
          .visual-stage {
            height: 520px;
          }
        }
        @media (max-width: 720px) {
          .site-header {
            padding: 22px 24px;
          }
          .site-brand {
            font-size: 26px;
          }
          .site-brand .aperture-logo {
            width: 42px;
            height: 42px;
          }
          .nav-actions a:first-child { display: none; }
          .nav-actions a.home-auth-link--signed-in { display: inline-flex; }
          .nav-actions a.home-auth-link--signed-in + a { display: none; }
          .nav-actions a:last-child {
            min-height: 44px;
            padding: 12px 18px;
          }
          .hero-section {
            align-items: start;
            min-height: 860px;
            padding-top: 132px;
          }
          .hero-grid--top { top: 120px; }
          .hero-mark {
            top: 180px;
            height: 160px;
          }
          .hero-word {
            font-size: clamp(5rem, 27vw, 7.8rem);
          }
          .hero-copy {
            transform: translateY(210px);
          }
          .hero-copy h1 {
            font-size: clamp(2rem, 10vw, 3.2rem);
            text-align: left;
          }
          .hero-copy p {
            text-align: left;
            font-size: 16px;
          }
          .prompt-bar {
            border-radius: 24px;
          }
          .prompt-text {
            padding: 15px 16px;
            font-size: 13px;
          }
          .prompt-button {
            width: 48px;
            height: 48px;
          }
          .hero-actions {
            justify-content: flex-start;
          }
          .section-shell,
          .product-reel-section,
          .faq-section {
            padding: 84px 24px;
          }
          .section-heading {
            display: block;
            margin-bottom: 34px;
          }
          .section-heading p {
            margin-top: 14px;
            font-size: 16px;
          }
          .capability-card {
            min-height: 320px;
            padding: 24px;
          }
          .capability-meta {
            margin-top: 160px;
          }
          .reel-copy h3 {
            font-size: clamp(2rem, 10vw, 3.3rem);
          }
          .reel-copy p {
            font-size: 16px;
          }
          .visual-stage {
            height: auto;
            min-height: 420px;
            transform: none;
          }
          .visual-stage--analysis {
            display: flex;
            flex-direction: column;
            gap: 18px;
          }
          .framed-shot,
          .framed-shot--panorama,
          .framed-shot--scenario,
          .framed-shot--wide {
            position: relative;
            left: auto;
            right: auto;
            top: auto;
            width: 100%;
            height: 360px;
            transform: none;
            opacity: .86;
            padding: 58px 12px 12px;
          }
          .framed-shot-caption {
            left: 12px;
            right: 12px;
            font-size: 12px;
          }
          .brand-portal {
            min-height: 780px;
            padding: 110px 24px;
          }
          .portal-grid {
            width: 760px;
          }
          .site-footer {
            flex-direction: column;
            align-items: flex-start;
            margin-inline: 24px;
          }
          .footer-links {
            flex-wrap: wrap;
          }
        }
        @media (prefers-reduced-motion: reduce) {
          .aperture-orbit,
          .aperture-scan,
          .hero-word--main,
          .space-dot,
          .reel-track,
          .portal-logo {
            animation: none;
          }
        }
      `}</style>

      <header className="site-header">
        <Link href="/" className="site-brand" aria-label="Specta AI 首页">
          <ApertureLogo compact />
          <span>Specta AI</span>
        </Link>
        <nav className="site-nav">
          <a href="#capabilities">平台能力</a>
          <a href="#product-reel">产品功能</a>
          <a href="#faq">Q&A</a>
        </nav>
        <HomeNavActions />
      </header>

      <HeroSignal />
      <CapabilitySection />
      <ProductReelSection />
      <BrandPortalSection />
      <FaqSection />

      <footer className="site-footer">
        <div>
          <Link href="/" className="site-brand" aria-label="Specta AI 首页">
            <ApertureLogo compact />
            <span>Specta AI</span>
          </Link>
          <p>AI品牌情报系统</p>
        </div>
        <div className="footer-links">
          <a href="#capabilities">平台能力</a>
          <a href="#product-reel">产品功能</a>
          <Link href="/auth?mode=apply">申请体验</Link>
        </div>
      </footer>
      <Script id="specta-heat-pointer" strategy="afterInteractive">
        {`
          (() => {
            document.querySelectorAll('[data-heat-target]').forEach((target) => {
              target.addEventListener('mousemove', (event) => {
                const rect = target.getBoundingClientRect();
                target.style.setProperty('--heat-x', event.clientX - rect.left + 'px');
                target.style.setProperty('--heat-y', event.clientY - rect.top + 'px');
              }, { passive: true });

              target.addEventListener('mouseleave', () => {
                target.style.setProperty('--heat-x', '50%');
                target.style.setProperty('--heat-y', '50%');
              }, { passive: true });
            });
          })();
        `}
      </Script>
    </main>
  );
}

export default HomePage;
