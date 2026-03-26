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
          className="h-16 rounded-[18px] border border-[#dde2e8] bg-white text-center text-[26px] font-semibold text-[#111827] outline-none transition-colors focus:border-[#111827]"
        />
      ))}
    </div>
  );
}

function ControlPlaneLoginContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextPath = useMemo(
    () => searchParams.get('next') || '/control-plane',
    [searchParams]
  );

  const [checking, setChecking] = useState(() => !!getStoredAccessToken());
  const [email, setEmail] = useState('');
  const [maskedEmail, setMaskedEmail] = useState('');
  const [code, setCode] = useState('');
  const [step, setStep] = useState<'email' | 'verify'>('email');
  const [countdown, setCountdown] = useState(0);
  const [isSendingCode, setIsSendingCode] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);

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
      toast.success('验证码已发送');
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
      <main className="flex min-h-screen items-center justify-center bg-[#f5f4ef]">
        <div className="text-center">
          <div className="mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-2 border-[#d7dbe3] border-t-[#111827]" />
          <p className="text-sm text-[#6b7280]">正在进入运营后台...</p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#f5f4ef]">
      <div className="mx-auto flex min-h-screen max-w-[760px] flex-col px-6 py-8 lg:px-10 lg:py-12">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <Link
              href="/"
              className="inline-flex items-center gap-2 text-sm font-medium text-[#475569]"
            >
              <RiArrowLeftLine className="h-4 w-4" />
              返回首页
            </Link>
            <PublicBrand size={34} textSizeClassName="text-[30px]" />
          </div>
        </div>

        <div className="mt-16">
          <div className="inline-flex items-center gap-2 rounded-full border border-[#e5e7eb] bg-white px-3 py-1.5 text-sm font-medium text-[#6b7280]">
            <RiShieldKeyholeLine className="h-4 w-4 text-[#4f46e5]" />
            运营后台
          </div>

          <h1 className="mt-8 text-[52px] font-semibold leading-[1.02] tracking-[-0.06em] text-[#111827] lg:text-[64px]">
            管理员邮箱验证码登录
          </h1>
          <p className="mt-4 max-w-[620px] text-[18px] leading-8 text-[#6b7280]">
            使用内部管理员邮箱获取验证码，验证后直接进入运营后台。
          </p>
        </div>

        <div className="mt-12 rounded-[32px] border border-[#e5e7eb] bg-white px-6 py-7 shadow-[0_24px_80px_rgba(35,31,26,0.08)] lg:px-8 lg:py-8">
          <div className="space-y-8">
            <label className="block">
              <div className="text-[17px] font-semibold text-[#111827]">管理员邮箱</div>
              <div className="mt-4">
                <div className="relative">
                  <RiMailLine className="pointer-events-none absolute left-5 top-1/2 h-5 w-5 -translate-y-1/2 text-[#94a3b8]" />
                  <input
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    inputMode="email"
                    autoComplete="email"
                    placeholder="you@company.com"
                    className="h-[60px] w-full rounded-[18px] border border-[#dde2e8] bg-white pl-12 pr-5 text-[18px] text-[#111827] outline-none transition-colors placeholder:text-[#a0a8b5] focus:border-[#111827]"
                  />
                </div>
              </div>
            </label>

            {step === 'verify' ? (
              <div>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-[17px] font-semibold text-[#111827]">验证码</div>
                    <div className="mt-2 text-sm text-[#6b7280]">
                      验证码已发送至 {maskedEmail}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={sendCode}
                    disabled={countdown > 0 || isSendingCode}
                    className="text-sm font-medium text-[#475569] disabled:cursor-not-allowed disabled:text-[#a0a8b5]"
                  >
                    {isSendingCode ? '发送中...' : formatCountdown(countdown)}
                  </button>
                </div>
                <div className="mt-4">
                  <CodeInputRow value={code} onChange={setCode} />
                </div>
              </div>
            ) : null}

            {currentUser && currentUser.role !== 'internal_admin' ? (
              <div className="rounded-[18px] border border-[rgba(191,146,91,0.24)] bg-[rgba(191,146,91,0.08)] px-4 py-3 text-sm leading-6 text-[#7c5a27]">
                当前账号不是运营后台管理员，请使用已授权的管理员邮箱登录。
              </div>
            ) : null}

            <div className="flex flex-wrap items-center gap-3">
              {step === 'verify' ? (
                <button
                  type="button"
                  onClick={login}
                  disabled={code.length !== CODE_LENGTH || isSubmitting}
                  className="inline-flex h-14 min-w-[180px] items-center justify-center rounded-[18px] bg-[#111827] px-6 text-base font-semibold text-white transition-colors disabled:cursor-not-allowed disabled:bg-[#eef1f5] disabled:text-[#a0a8b5]"
                >
                  {isSubmitting ? '登录中...' : '进入后台'}
                </button>
              ) : (
                <button
                  type="button"
                  onClick={sendCode}
                  disabled={!normalizeEmail(email) || isSendingCode}
                  className="inline-flex h-14 min-w-[180px] items-center justify-center rounded-[18px] bg-[#111827] px-6 text-base font-semibold text-white transition-colors disabled:cursor-not-allowed disabled:bg-[#eef1f5] disabled:text-[#a0a8b5]"
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
                    setCountdown(0);
                  }}
                  className="inline-flex h-14 items-center justify-center rounded-[18px] border border-[#dde2e8] px-5 text-sm font-medium text-[#475569]"
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
