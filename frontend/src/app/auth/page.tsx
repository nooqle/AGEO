'use client';

import { Suspense, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  RiArrowLeftLine,
  RiBuildingLine,
  RiPassValidLine,
  RiShieldCheckLine,
} from '@remixicon/react';
import { api } from '@/services/api';
import { clearStoredAccessToken, getStoredAccessToken, setStoredAccessToken } from '@/lib/auth-storage';
import { toast } from '@/components/ui/toast';
import type { VerificationChannel } from '@/types/auth';

type AuthMode = 'login' | 'register';
const EMAIL_CHANNEL: VerificationChannel = 'email';

function normalizeTarget(channel: VerificationChannel, value: string) {
  const trimmed = value.trim();
  return channel === 'email' ? trimmed.toLowerCase() : trimmed;
}

function formatCountdown(value: number) {
  if (value <= 0) return '重新发送验证码';
  return `${value}s 后可重发`;
}

function AuthPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextPath = useMemo(() => searchParams.get('next') || '/dashboard', [searchParams]);

  const [mode, setMode] = useState<AuthMode>('login');
  const [isSendingCode, setIsSendingCode] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [debugCode, setDebugCode] = useState<string | null>(null);

  const [loginTarget, setLoginTarget] = useState('');
  const [loginCode, setLoginCode] = useState('');

  const [registrationEmail, setRegistrationEmail] = useState('');
  const [registrationPhone, setRegistrationPhone] = useState('');
  const [registrationCode, setRegistrationCode] = useState('');
  const [organizationName, setOrganizationName] = useState('');
  const [jobTitle, setJobTitle] = useState('');
  const [applicantName, setApplicantName] = useState('');
  const [pendingReviewMessage, setPendingReviewMessage] = useState<string | null>(null);

  useEffect(() => {
    const storedToken = getStoredAccessToken();
    if (!storedToken) return;
    api.getMe()
      .then(() => {
        router.replace(nextPath);
      })
      .catch(() => {
        clearStoredAccessToken();
      });
  }, [nextPath, router]);

  useEffect(() => {
    if (countdown <= 0) return;
    const timer = window.setTimeout(() => setCountdown((value) => value - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [countdown]);

  const activeTarget = mode === 'login'
    ? loginTarget
    : registrationEmail;

  const canSendCode = normalizeTarget(EMAIL_CHANNEL, activeTarget).length > 0 && countdown === 0 && !isSendingCode;

  const handleSendCode = async () => {
    const normalizedTarget = normalizeTarget(EMAIL_CHANNEL, activeTarget);
    if (!normalizedTarget) {
      toast.error('请先输入邮箱地址');
      return;
    }
    setIsSendingCode(true);
    setDebugCode(null);
    try {
      const response = await api.sendVerificationCode({
        channel: EMAIL_CHANNEL,
        purpose: mode === 'login' ? 'login' : 'registration',
        target: normalizedTarget,
      });
      setCountdown(Math.max(30, Math.min(response.expires_in_seconds, 60)));
      setDebugCode(response.debug_code ?? null);
      toast.success('验证码已发送');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '验证码发送失败');
    } finally {
      setIsSendingCode(false);
    }
  };

  const handleLogin = async (event: React.FormEvent) => {
    event.preventDefault();
    const normalizedTarget = normalizeTarget(EMAIL_CHANNEL, loginTarget);
    if (!normalizedTarget || !loginCode.trim()) {
      toast.error('请先填写账号和验证码');
      return;
    }
    setIsSubmitting(true);
    setPendingReviewMessage(null);
    try {
      const response = await api.loginWithOtp({
        channel: EMAIL_CHANNEL,
        target: normalizedTarget,
        verification_code: loginCode.trim(),
      });
      setStoredAccessToken(response.access_token);
      toast.success('登录成功');
      router.replace(nextPath);
    } catch (error) {
      const message = error instanceof Error ? error.message : '登录失败';
      if (message.includes('待审核')) {
        setPendingReviewMessage(message);
      }
      toast.error(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRegister = async (event: React.FormEvent) => {
    event.preventDefault();
    const normalizedTarget = normalizeTarget(EMAIL_CHANNEL, registrationEmail);
    if (!normalizedTarget || !registrationCode.trim() || !organizationName.trim() || !jobTitle.trim()) {
      toast.error('请先完整填写注册信息');
      return;
    }
    setIsSubmitting(true);
    try {
      await api.createRegistrationApplication({
        email: registrationEmail.trim() ? registrationEmail.trim().toLowerCase() : null,
        phone: registrationPhone.trim() || null,
        verification_channel: EMAIL_CHANNEL,
        verification_target: normalizedTarget,
        verification_code: registrationCode.trim(),
        organization_name: organizationName.trim(),
        job_title: jobTitle.trim(),
        applicant_name: applicantName.trim() || null,
      });
      setPendingReviewMessage('注册申请已提交，请等待后台审核开通后再登录。');
      setRegistrationCode('');
      toast.success('注册申请已提交');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '提交注册申请失败');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="min-h-screen overflow-hidden" style={{ backgroundColor: 'var(--bg-primary)' }}>
      <div
        className="relative min-h-screen"
        style={{
          background:
            'radial-gradient(circle at top left, color-mix(in srgb, var(--color-primary) 16%, transparent) 0%, transparent 38%), radial-gradient(circle at bottom right, rgba(191, 146, 91, 0.14) 0%, transparent 34%), var(--bg-primary)',
        }}
      >
        <div className="mx-auto grid min-h-screen max-w-7xl gap-10 px-4 py-8 lg:grid-cols-[1.05fr_0.95fr] lg:px-8">
          <section className="flex flex-col justify-between rounded-[32px] border px-6 py-7 lg:px-8 lg:py-9" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'color-mix(in srgb, var(--bg-secondary) 92%, white 8%)' }}>
            <div>
              <Link
                href="/"
                className="inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs transition-colors"
                style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-secondary)' }}
              >
                <RiArrowLeftLine className="h-3.5 w-3.5" />
                返回首页
              </Link>

              <div className="mt-8 max-w-xl">
                <div className="inline-flex rounded-full border px-3 py-1 text-[11px] tracking-[0.22em]" style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-tertiary)' }}>
                  SPECTA ACCESS
                </div>
                <h1 className="mt-5 text-4xl font-semibold tracking-[-0.04em] lg:text-5xl" style={{ color: 'var(--text-primary)' }}>
                  提交身份与组织信息
                </h1>
                <p className="mt-4 max-w-2xl text-sm leading-7 lg:text-[15px]" style={{ color: 'var(--text-secondary)' }}>
                    使用邮箱验证码登录。注册申请审核通过后开通账号；组织空间与个人空间数据彼此隔离。
                </p>
              </div>
            </div>

            <div className="grid gap-4 lg:max-w-xl">
              {[
                {
                  icon: <RiPassValidLine className="h-4 w-4" />,
                    title: '人工审核开通',
                    description: '注册申请审核通过后开通账号。',
                },
                {
                  icon: <RiBuildingLine className="h-4 w-4" />,
                  title: '组织空间共享',
                  description: '同组织账号后续可以共享组织空间下的品牌采集与历史分析资产，减少重复抓取。',
                },
                {
                  icon: <RiShieldCheckLine className="h-4 w-4" />,
                  title: '个人空间隔离',
                  description: '个人空间品牌只对本人可见，适合试验性分析和未准备对组织公开的品牌数据。',
                },
              ].map((item) => (
                <div
                  key={item.title}
                  className="rounded-[24px] border px-5 py-4"
                  style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}
                >
                  <div className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    <span className="inline-flex h-8 w-8 items-center justify-center rounded-full" style={{ backgroundColor: 'color-mix(in srgb, var(--color-primary) 12%, var(--bg-primary) 88%)', color: 'var(--color-primary)' }}>
                      {item.icon}
                    </span>
                    {item.title}
                  </div>
                  <p className="mt-3 text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
                    {item.description}
                  </p>
                </div>
              ))}
            </div>
          </section>

          <section className="flex items-center justify-center">
            <div
              className="w-full max-w-xl rounded-[32px] border p-6 shadow-[0_24px_80px_rgba(35,31,26,0.08)] lg:p-7"
              style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'color-mix(in srgb, var(--bg-secondary) 95%, white 5%)' }}
            >
              <div className="grid grid-cols-2 gap-2 rounded-[20px] border p-1" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-primary)' }}>
                {[
                  { key: 'login', label: '验证码登录' },
                  { key: 'register', label: '注册申请' },
                ].map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => {
                      setMode(item.key as AuthMode);
                      setDebugCode(null);
                    }}
                    className="rounded-[16px] px-4 py-3 text-sm font-medium transition-colors"
                    style={{
                      backgroundColor: mode === item.key ? 'var(--bg-secondary)' : 'transparent',
                      color: mode === item.key ? 'var(--text-primary)' : 'var(--text-secondary)',
                    }}
                  >
                    {item.label}
                  </button>
                ))}
              </div>

              <div className="mt-4 rounded-[20px] border px-4 py-3 text-xs leading-6" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-secondary)' }}>
                当前支持邮箱验证码登录；手机号仅作为联系信息保存。
              </div>

              {mode === 'login' ? (
                <form className="mt-6 space-y-4" onSubmit={handleLogin}>
                  <div>
                    <label className="mb-1.5 block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                      邮箱地址
                    </label>
                    <input
                      type="email"
                      value={loginTarget}
                      onChange={(event) => setLoginTarget(event.target.value)}
                      placeholder="you@company.com"
                      className="w-full rounded-[16px] border px-4 py-3 text-sm outline-none transition-colors"
                      style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                    />
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                      验证码
                    </label>
                    <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
                      <input
                        type="text"
                        value={loginCode}
                        onChange={(event) => setLoginCode(event.target.value)}
                        placeholder="输入 6 位验证码"
                        className="w-full rounded-[16px] border px-4 py-3 text-sm outline-none transition-colors"
                        style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                      />
                      <button
                        type="button"
                        onClick={handleSendCode}
                        disabled={!canSendCode}
                        className="rounded-[16px] px-4 py-3 text-sm font-medium transition-opacity disabled:cursor-not-allowed disabled:opacity-50"
                        style={{ backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-primary)' }}
                      >
                        {isSendingCode ? '发送中...' : formatCountdown(countdown)}
                      </button>
                    </div>
                  </div>

                  {pendingReviewMessage && (
                    <div className="rounded-[18px] border px-4 py-3 text-sm leading-6" style={{ borderColor: 'rgba(191, 146, 91, 0.22)', backgroundColor: 'rgba(191, 146, 91, 0.08)', color: 'var(--text-secondary)' }}>
                      {pendingReviewMessage}
                    </div>
                  )}

                  {debugCode && (
                    <div className="rounded-[18px] border px-4 py-3 text-sm" style={{ borderColor: 'rgba(54, 79, 124, 0.22)', backgroundColor: 'rgba(54, 79, 124, 0.08)', color: 'var(--text-primary)' }}>
                      开发环境验证码：<span className="font-semibold tracking-[0.16em]">{debugCode}</span>
                    </div>
                  )}

                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="w-full rounded-[18px] px-4 py-3 text-sm font-medium text-white transition-opacity disabled:cursor-not-allowed disabled:opacity-60"
                    style={{
                      background: 'linear-gradient(180deg, color-mix(in srgb, var(--color-primary) 88%, #8092ff 12%), color-mix(in srgb, var(--color-primary) 74%, #4458d7 26%))',
                    }}
                  >
                    {isSubmitting ? '登录中...' : '进入工作台'}
                  </button>
                </form>
              ) : (
                <form className="mt-6 space-y-4" onSubmit={handleRegister}>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <label className="mb-1.5 block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                        邮箱
                      </label>
                      <input
                        type="email"
                        value={registrationEmail}
                        onChange={(event) => setRegistrationEmail(event.target.value)}
                        placeholder="you@company.com"
                        className="w-full rounded-[16px] border px-4 py-3 text-sm outline-none transition-colors"
                        style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                      />
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                        手机号（选填）
                      </label>
                      <input
                        type="tel"
                        value={registrationPhone}
                        onChange={(event) => setRegistrationPhone(event.target.value)}
                        placeholder="13800000000"
                        className="w-full rounded-[16px] border px-4 py-3 text-sm outline-none transition-colors"
                        style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                      />
                    </div>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <label className="mb-1.5 block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                        公司 / 组织全称
                      </label>
                      <input
                        type="text"
                        value={organizationName}
                        onChange={(event) => setOrganizationName(event.target.value)}
                        placeholder="例如：上海某某科技有限公司"
                        className="w-full rounded-[16px] border px-4 py-3 text-sm outline-none transition-colors"
                        style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                      />
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                        申请人职位
                      </label>
                      <input
                        type="text"
                        value={jobTitle}
                        onChange={(event) => setJobTitle(event.target.value)}
                        placeholder="例如：品牌负责人"
                        className="w-full rounded-[16px] border px-4 py-3 text-sm outline-none transition-colors"
                        style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                      />
                    </div>
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                      申请人姓名（选填）
                    </label>
                    <input
                      type="text"
                      value={applicantName}
                      onChange={(event) => setApplicantName(event.target.value)}
                      placeholder="例如：张三"
                      className="w-full rounded-[16px] border px-4 py-3 text-sm outline-none transition-colors"
                      style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                    />
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                      邮箱验证码
                    </label>
                    <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
                      <input
                        type="text"
                        value={registrationCode}
                        onChange={(event) => setRegistrationCode(event.target.value)}
                        placeholder="输入 6 位验证码"
                        className="w-full rounded-[16px] border px-4 py-3 text-sm outline-none transition-colors"
                        style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                      />
                      <button
                        type="button"
                        onClick={handleSendCode}
                        disabled={!canSendCode}
                        className="rounded-[16px] px-4 py-3 text-sm font-medium transition-opacity disabled:cursor-not-allowed disabled:opacity-50"
                        style={{ backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-primary)' }}
                      >
                        {isSendingCode ? '发送中...' : formatCountdown(countdown)}
                      </button>
                    </div>
                  </div>

                  {pendingReviewMessage && (
                    <div className="rounded-[18px] border px-4 py-3 text-sm leading-6" style={{ borderColor: 'rgba(54, 79, 124, 0.22)', backgroundColor: 'rgba(54, 79, 124, 0.08)', color: 'var(--text-secondary)' }}>
                      {pendingReviewMessage}
                    </div>
                  )}

                  {debugCode && (
                    <div className="rounded-[18px] border px-4 py-3 text-sm" style={{ borderColor: 'rgba(54, 79, 124, 0.22)', backgroundColor: 'rgba(54, 79, 124, 0.08)', color: 'var(--text-primary)' }}>
                      开发环境验证码：<span className="font-semibold tracking-[0.16em]">{debugCode}</span>
                    </div>
                  )}

                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="w-full rounded-[18px] px-4 py-3 text-sm font-medium text-white transition-opacity disabled:cursor-not-allowed disabled:opacity-60"
                    style={{
                      background: 'linear-gradient(180deg, color-mix(in srgb, var(--color-primary) 88%, #8092ff 12%), color-mix(in srgb, var(--color-primary) 74%, #4458d7 26%))',
                    }}
                  >
                    {isSubmitting ? '提交中...' : '提交注册申请'}
                  </button>
                </form>
              )}

                <div className="mt-6 rounded-[20px] border px-4 py-3 text-xs leading-6" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-secondary)' }}>
                  {mode === 'login'
                    ? '未开通账号会提示“待审核开通”。'
                    : '注册申请提交后需等待审核通过。'}
                </div>
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}

export default function AuthPage() {
  return (
    <Suspense>
      <AuthPageContent />
    </Suspense>
  );
}
