'use client';

import Link from 'next/link';
import { Suspense, useEffect, useMemo, useRef, useState, type ClipboardEvent } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  RiArrowLeftLine,
  RiMailLine,
  RiShieldKeyholeLine,
} from '@remixicon/react';

import { PublicBrand } from '@/components/layout/PublicBrand';
import { toast } from '@/components/ui/toast';
import {
  clearStoredAccessToken,
  getStoredAccessToken,
  setStoredAccessToken,
} from '@/lib/auth-storage';
import { consumeAuthRedirectToast, resolveAuthNextPath } from '@/lib/auth-expiry';
import { api } from '@/services/api';
import type { AuthUser, VerificationChannel } from '@/types/auth';

const EMAIL_CHANNEL: VerificationChannel = 'email';
const CODE_LENGTH = 6;

function normalizeEmail(value: string) {
  return value.trim().toLowerCase();
}

function sanitizeDigits(value: string) {
  return value.replace(/\D/g, '').slice(0, CODE_LENGTH);
}

function maskEmail(email: string) {
  const normalized = normalizeEmail(email);
  const [localPart = '', domain = ''] = normalized.split('@');
  if (!localPart || !domain) return normalized;
  if (localPart.length <= 2) return `${localPart[0] || '*'}***@${domain}`;
  return `${localPart.slice(0, 2)}***@${domain}`;
}

function formatCountdown(seconds: number) {
  if (seconds <= 0) return '发送验证码';
  return `${seconds}s 后可重发`;
}

function CodeInputRow({
  value,
  onChange,
}: {
  value: string;
  onChange: (next: string) => void;
}) {
  const inputsRef = useRef<Array<HTMLInputElement | null>>([]);

  const handleInput = (index: number, rawValue: string) => {
    const digit = rawValue.replace(/\D/g, '').slice(-1);
    const next = value.split('');
    next[index] = digit;
    onChange(next.join('').slice(0, CODE_LENGTH));
    if (digit && index < CODE_LENGTH - 1) {
      inputsRef.current[index + 1]?.focus();
    }
  };

  const handleBackspace = (index: number) => {
    if (!value[index] && index > 0) {
      inputsRef.current[index - 1]?.focus();
    }
  };

  const handlePaste = (event: ClipboardEvent<HTMLDivElement>) => {
    event.preventDefault();
    onChange(sanitizeDigits(event.clipboardData.getData('text')));
  };

  return (
    <div className="grid grid-cols-6 gap-3" onPaste={handlePaste}>
      {Array.from({ length: CODE_LENGTH }).map((_, index) => (
        <input
          key={index}
          ref={(node) => {
            inputsRef.current[index] = node;
          }}
          inputMode="numeric"
          autoComplete="one-time-code"
          value={value[index] || ''}
          onChange={(event) => handleInput(index, event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Backspace') {
              handleBackspace(index);
            }
          }}
          className="h-14 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] text-center text-[22px] font-semibold text-[var(--text-primary)] outline-none transition-colors focus:border-[var(--brand-primary)]"
        />
      ))}
    </div>
  );
}

function ControlPlaneLoginContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextPath = useMemo(
    () => resolveAuthNextPath(searchParams.get('next'), '/control-plane'),
    [searchParams]
  );

  const [checking, setChecking] = useState(() => !!getStoredAccessToken());
  const [email, setEmail] = useState('');
  const [maskedEmail, setMaskedEmail] = useState('');
  const [code, setCode] = useState('');
  const [debugCode, setDebugCode] = useState<string | null>(null);
  const [step, setStep] = useState<'email' | 'verify'>('email');
  const [countdown, setCountdown] = useState(0);
  const [isSendingCode, setIsSendingCode] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    const message = consumeAuthRedirectToast();
    if (message) {
      toast.error(message, 3000);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const token = getStoredAccessToken();
    if (!token) {
      setChecking(false);
      return;
    }

    api
      .getMe()
      .then((user) => {
        if (cancelled) return;
        if (user.role === 'internal_admin') {
          router.replace(nextPath);
          return;
        }
        clearStoredAccessToken();
        setCurrentUser(user);
        setChecking(false);
      })
      .catch(() => {
        if (cancelled) return;
        clearStoredAccessToken();
        setChecking(false);
      });

    return () => {
      cancelled = true;
    };
  }, [nextPath, router]);

  useEffect(() => {
    if (countdown <= 0) return;
    const timer = window.setTimeout(() => setCountdown((value) => value - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [countdown]);

  const sendCode = async () => {
    const normalizedEmail = normalizeEmail(email);
    if (!normalizedEmail) {
      toast.error('请输入管理员邮箱');
      return;
    }
    setIsSendingCode(true);
    setDebugCode(null);
    try {
      const response = await api.sendVerificationCode({
        channel: EMAIL_CHANNEL,
        purpose: 'login',
        target: normalizedEmail,
      });
      setMaskedEmail(maskEmail(normalizedEmail));
      setStep('verify');
      setCountdown(Math.max(30, Math.min(response.expires_in_seconds, 60)));
      setCode('');
      setDebugCode(response.debug_code ?? null);
      toast.success(
        response.debug_code
          ? `验证码已生成，开发验证码：${response.debug_code}`
          : '验证码已发送'
      );
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '验证码发送失败');
    } finally {
      setIsSendingCode(false);
    }
  };

  const login = async () => {
    const normalizedEmail = normalizeEmail(email);
    if (!normalizedEmail) {
      toast.error('请输入管理员邮箱');
      return;
    }
    if (code.length !== CODE_LENGTH) {
      toast.error('请输入 6 位验证码');
      return;
    }

    setIsSubmitting(true);
    try {
      const token = await api.loginWithOtp({
        channel: EMAIL_CHANNEL,
        target: normalizedEmail,
        verification_code: code,
      });
      setStoredAccessToken(token.access_token);
      const user = await api.getMe();
      if (user.role !== 'internal_admin') {
        clearStoredAccessToken();
        setCurrentUser(user);
        throw new Error('当前账号没有运营后台权限');
      }
      router.replace(nextPath);
    } catch (error) {
      clearStoredAccessToken();
      toast.error(error instanceof Error ? error.message : '登录失败');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (checking) {
    return (
      <main className="public-light-surface flex min-h-screen items-center justify-center bg-[var(--bg-primary)]">
        <div className="text-center">
          <div className="mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-2 border-[var(--border-subtle)] border-t-[var(--brand-primary)]" />
          <p className="text-sm text-[var(--text-secondary)]">正在进入运营后台...</p>
        </div>
      </main>
    );
  }

  return (
    <main className="public-light-surface min-h-screen bg-[var(--bg-primary)]">
      <div className="mx-auto flex min-h-screen max-w-[760px] flex-col px-6 py-8 lg:px-10 lg:py-12">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <Link
              href="/"
              className="inline-flex items-center gap-2 text-sm font-medium text-[var(--text-secondary)]"
            >
              <RiArrowLeftLine className="h-4 w-4" />
              返回首页
            </Link>
            <PublicBrand size={34} textSizeClassName="text-[30px]" />
          </div>
        </div>

        <div className="mt-16">
          <div className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-1.5 text-sm font-medium text-[var(--text-secondary)]">
            <RiShieldKeyholeLine className="h-4 w-4 text-[var(--brand-text)]" />
            运营后台
          </div>

          <h1 className="mt-8 text-[36px] font-semibold leading-[1.12] text-[var(--text-primary)] lg:text-[46px]">
            管理员邮箱验证码登录
          </h1>
          <p className="mt-4 max-w-[620px] text-[16px] leading-8 text-[var(--text-secondary)]">
            使用内部管理员邮箱获取验证码，验证后直接进入运营后台。
          </p>
        </div>

        <div className="mt-10 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-6 py-7 shadow-sm lg:px-8 lg:py-8">
          <div className="space-y-8">
            <label className="block">
              <div className="text-[15px] font-semibold text-[var(--text-primary)]">管理员邮箱</div>
              <div className="mt-4">
                <div className="relative">
                  <RiMailLine className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-[var(--text-tertiary)]" />
                  <input
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    inputMode="email"
                    autoComplete="email"
                    placeholder="you@company.com"
                    className="h-12 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] pl-11 pr-4 text-[15px] text-[var(--text-primary)] outline-none transition-colors placeholder:text-[var(--text-tertiary)] focus:border-[var(--brand-primary)]"
                  />
                </div>
              </div>
            </label>

            {step === 'verify' ? (
              <div>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-[15px] font-semibold text-[var(--text-primary)]">验证码</div>
                    <div className="mt-2 text-sm text-[var(--text-secondary)]">
                      验证码已发送至 {maskedEmail}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={sendCode}
                    disabled={countdown > 0 || isSendingCode}
                    className="text-sm font-medium text-[var(--text-secondary)] disabled:cursor-not-allowed disabled:text-[var(--text-disabled)]"
                  >
                    {isSendingCode ? '发送中...' : formatCountdown(countdown)}
                  </button>
                </div>
                <div className="mt-4">
                  <CodeInputRow value={code} onChange={setCode} />
                </div>
                {debugCode ? (
                  <div className="mt-4 rounded-xl border border-[var(--border-subtle)] bg-[var(--status-info-bg)] px-4 py-3 text-sm leading-6 text-[var(--text-secondary)]">
                    <div className="font-semibold text-[var(--info)]">开发环境验证码</div>
                    <div className="mt-1">
                      当前管理员邮箱验证码是 <span className="font-mono text-base font-semibold">{debugCode}</span>
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}

            {currentUser && currentUser.role !== 'internal_admin' ? (
              <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--status-warning-bg)] px-4 py-3 text-sm leading-6 text-[var(--text-secondary)]">
                当前账号不是运营后台管理员，请使用已授权的管理员邮箱登录。
              </div>
            ) : null}

            <div className="flex flex-wrap items-center gap-3">
              {step === 'verify' ? (
                <button
                  type="button"
                  onClick={login}
                  disabled={code.length !== CODE_LENGTH || isSubmitting}
                  className="inline-flex h-12 min-w-[180px] items-center justify-center rounded-xl bg-[var(--brand-primary)] px-6 text-base font-semibold text-[var(--brand-contrast)] transition-colors hover:bg-[var(--brand-hover)] disabled:cursor-not-allowed disabled:bg-[var(--bg-tertiary)] disabled:text-[var(--text-disabled)]"
                >
                  {isSubmitting ? '登录中...' : '进入后台'}
                </button>
              ) : (
                <button
                  type="button"
                  onClick={sendCode}
                  disabled={!normalizeEmail(email) || isSendingCode}
                  className="inline-flex h-12 min-w-[180px] items-center justify-center rounded-xl bg-[var(--brand-primary)] px-6 text-base font-semibold text-[var(--brand-contrast)] transition-colors hover:bg-[var(--brand-hover)] disabled:cursor-not-allowed disabled:bg-[var(--bg-tertiary)] disabled:text-[var(--text-disabled)]"
                >
                  {isSendingCode ? '发送中...' : '发送验证码'}
                </button>
              )}

              {step === 'verify' ? (
                <button
                  type="button"
                  onClick={() => {
                    setStep('email');
                    setCode('');
                    setDebugCode(null);
                    setCountdown(0);
                  }}
                  className="inline-flex h-12 items-center justify-center rounded-xl border border-[var(--border-subtle)] px-5 text-sm font-medium text-[var(--text-secondary)]"
                >
                  更换邮箱
                </button>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}

export default function ControlPlaneLoginPage() {
  return (
    <Suspense>
      <ControlPlaneLoginContent />
    </Suspense>
  );
}
