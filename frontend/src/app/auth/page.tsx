'use client';

import {
  Suspense,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type ClipboardEvent,
  type InputHTMLAttributes,
  type KeyboardEvent,
  type ReactNode,
} from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  RiArrowLeftLine,
  RiArrowRightLine,
  RiMailLine,
  RiShieldKeyholeLine,
} from '@remixicon/react';

import { toast } from '@/components/ui/toast';
import {
  clearStoredAccessToken,
  getStoredAccessToken,
  setStoredAccessToken,
} from '@/lib/auth-storage';
import { consumeAuthRedirectToast } from '@/lib/auth-expiry';
import { PublicBrand } from '@/components/layout/PublicBrand';
import { api } from '@/services/api';
import type { VerificationChannel } from '@/types/auth';

const EMAIL_CHANNEL: VerificationChannel = 'email';
const CODE_LENGTH = 6;

const companySizeOptions = [
  '1-10 人',
  '11-50 人',
  '51-200 人',
  '201-500 人',
  '500 人以上',
];

type Mode = 'apply' | 'login';
type Step = 'company' | 'verify' | 'invite' | 'login-email' | 'login-verify';

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

function formatCountdown(seconds: number, label: string) {
  if (seconds <= 0) return label;
  return `${seconds}s 后可重新发送`;
}

function PageHeader({
  mode,
  onModeChange,
}: {
  mode: Mode;
  onModeChange: (next: Mode) => void;
}) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-4">
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

      <div className="inline-flex rounded-full border border-[#e5e7eb] bg-white p-1">
        <button
          type="button"
          onClick={() => onModeChange('apply')}
          className={`rounded-full px-4 py-2 text-sm font-semibold transition-colors ${
            mode === 'apply'
              ? 'bg-[#111827] text-white'
              : 'text-[#475569]'
          }`}
        >
          申请体验
        </button>
        <button
          type="button"
          onClick={() => onModeChange('login')}
          className={`rounded-full px-4 py-2 text-sm font-semibold transition-colors ${
            mode === 'login'
              ? 'bg-[#111827] text-white'
              : 'text-[#475569]'
          }`}
        >
          已有账号
        </button>
      </div>
    </header>
  );
}

function StepHeader({
  mode,
  step,
  title,
  description,
}: {
  mode: Mode;
  step: number;
  title: string;
  description: string;
}) {
  const total = mode === 'apply' ? 3 : 2;
  const labels =
    mode === 'apply'
      ? ['公司信息', '验证邮箱', '输入邀请码']
      : ['工作邮箱', '登录验证'];
  return (
    <div className="max-w-[720px]">
      <div className="inline-flex items-center gap-3 rounded-full border border-[#e5e7eb] bg-white px-3 py-1.5 text-sm text-[#6b7280]">
        <span className="font-semibold text-[#111827]">
          {String(step).padStart(2, '0')}
        </span>
        <span>/</span>
        <span>{String(total).padStart(2, '0')}</span>
      </div>
      <div className="mt-5 flex flex-wrap gap-3">
        {labels.map((label, index) => {
          const current = index + 1 === step;
          const completed = index + 1 < step;
          return (
            <div
              key={label}
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-medium ${
                current
                  ? 'border-[#111827] bg-[#111827] text-white'
                  : completed
                    ? 'border-[#d7dbe3] bg-white text-[#111827]'
                    : 'border-[#e5e7eb] bg-white text-[#94a3b8]'
              }`}
            >
              <span className="font-semibold">
                {String(index + 1).padStart(2, '0')}
              </span>
              <span>{label}</span>
            </div>
          );
        })}
      </div>
      <h1 className="mt-8 text-[44px] font-semibold leading-[1.02] tracking-[-0.06em] text-[#111827] lg:text-[56px]">
        {title}
      </h1>
      <p className="mt-4 max-w-[620px] text-[18px] leading-8 text-[#6b7280]">
        {description}
      </p>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <div className="text-[17px] font-semibold text-[#111827]">{label}</div>
      <div className="mt-4">{children}</div>
    </label>
  );
}

function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`h-[60px] w-full rounded-[18px] border border-[#dde2e8] bg-white px-5 text-[18px] text-[#111827] outline-none transition-colors placeholder:text-[#a0a8b5] focus:border-[#111827] ${props.className || ''}`}
    />
  );
}

function OptionButton({
  active,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  active: boolean;
  children: ReactNode;
}) {
  return (
    <button
      {...props}
      type="button"
      className={`rounded-[18px] border px-5 py-4 text-left text-[18px] font-semibold transition-colors ${
        active
          ? 'border-[#111827] bg-[#f8fafc] text-[#111827]'
          : 'border-[#dde2e8] bg-white text-[#111827] hover:border-[#c6ccd5]'
      } ${props.className || ''}`}
    >
      {children}
    </button>
  );
}

function PrimaryButton({
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
}) {
  return (
    <button
      {...props}
      className={`inline-flex h-14 w-full items-center justify-center rounded-[18px] bg-[#111827] px-6 text-base font-semibold text-white transition-colors disabled:cursor-not-allowed disabled:bg-[#eef1f5] disabled:text-[#a0a8b5] ${props.className || ''}`}
    >
      {children}
    </button>
  );
}

function SecondaryAction({
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
}) {
  return (
    <button
      {...props}
      type="button"
      className={`inline-flex items-center justify-center text-sm font-medium text-[#475569] disabled:cursor-not-allowed disabled:text-[#a0a8b5] ${props.className || ''}`}
    >
      {children}
    </button>
  );
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

  const handleKeyDown = (index: number, event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Backspace' && !value[index] && index > 0) {
      inputsRef.current[index - 1]?.focus();
    }
  };

  const handlePaste = (event: ClipboardEvent<HTMLDivElement>) => {
    event.preventDefault();
    onChange(sanitizeDigits(event.clipboardData.getData('text')));
  };

  return (
    <div className="grid max-w-[660px] grid-cols-6 gap-3" onPaste={handlePaste}>
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
          onKeyDown={(event) => handleKeyDown(index, event)}
          className="h-20 rounded-[18px] border border-[#dde2e8] bg-white text-center text-[30px] font-semibold text-[#111827] outline-none transition-colors focus:border-[#111827]"
        />
      ))}
    </div>
  );
}

function InfoPanel({
  icon,
  title,
  description,
}: {
  icon: ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-[20px] border border-[#e5e7eb] bg-white px-5 py-5">
      <div className="flex items-start gap-4">
        <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#eef2ff] text-[#4f46e5]">
          {icon}
        </div>
        <div>
          <div className="text-sm font-semibold text-[#111827]">{title}</div>
          <div className="mt-2 text-sm leading-7 text-[#6b7280]">{description}</div>
        </div>
      </div>
    </div>
  );
}

function AuthPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextPath = useMemo(() => searchParams.get('next') || '/dashboard', [searchParams]);
  const requestedMode = useMemo<Mode>(
    () => (searchParams.get('mode') === 'login' ? 'login' : 'apply'),
    [searchParams]
  );

  const [mode, setMode] = useState<Mode>(requestedMode);
  const [step, setStep] = useState<Step>(
    requestedMode === 'login' ? 'login-email' : 'company'
  );
  const [countdown, setCountdown] = useState(0);
  const [isSendingCode, setIsSendingCode] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [companyName, setCompanyName] = useState('');
  const [companySize, setCompanySize] = useState(companySizeOptions[1]);
  const [isAgency, setIsAgency] = useState(false);
  const [registrationEmail, setRegistrationEmail] = useState('');
  const [registrationCode, setRegistrationCode] = useState('');
  const [registrationDebugCode, setRegistrationDebugCode] = useState<string | null>(null);
  const [inviteCode, setInviteCode] = useState('');

  const [loginEmail, setLoginEmail] = useState('');
  const [loginCode, setLoginCode] = useState('');
  const [loginDebugCode, setLoginDebugCode] = useState<string | null>(null);

  useEffect(() => {
    const message = consumeAuthRedirectToast();
    if (message) {
      toast.error(message, 3000);
    }
  }, []);

  useEffect(() => {
    const storedToken = getStoredAccessToken();
    if (!storedToken) return;
    api
      .getMe()
      .then(() => {
        router.replace(nextPath);
      })
      .catch(() => {
        clearStoredAccessToken();
      });
  }, [nextPath, router]);

  useEffect(() => {
    setMode(requestedMode);
    setCountdown(0);
    setIsSendingCode(false);
    setIsSubmitting(false);
    setRegistrationDebugCode(null);
    setLoginDebugCode(null);
    setStep(requestedMode === 'login' ? 'login-email' : 'company');
  }, [requestedMode]);

  useEffect(() => {
    if (countdown <= 0) return;
    const timer = window.setTimeout(() => setCountdown((current) => current - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [countdown]);

  const canSendRegistrationCode =
    normalizeEmail(registrationEmail).length > 0 &&
    companyName.trim().length >= 2 &&
    companySize.length > 0 &&
    countdown === 0 &&
    !isSendingCode;

  const canSendLoginCode =
    normalizeEmail(loginEmail).length > 0 && countdown === 0 && !isSendingCode;

  const changeMode = (next: Mode) => {
    const query = new URLSearchParams();
    query.set('mode', next);
    if (nextPath && nextPath !== '/dashboard') {
      query.set('next', nextPath);
    }
    router.replace(`/auth?${query.toString()}`);
    setMode(next);
    setCountdown(0);
    setIsSendingCode(false);
    setIsSubmitting(false);
    setStep(next === 'apply' ? 'company' : 'login-email');
  };

  const handleSendRegistrationCode = async () => {
    const email = normalizeEmail(registrationEmail);
    if (!email || companyName.trim().length < 2 || !companySize) {
      toast.error('请先填写公司信息和工作邮箱');
      return;
    }
    setIsSendingCode(true);
    setRegistrationDebugCode(null);
    try {
      const response = await api.sendVerificationCode({
        channel: EMAIL_CHANNEL,
        purpose: 'registration',
        target: email,
      });
      setCountdown(Math.max(30, Math.min(response.expires_in_seconds, 60)));
      setRegistrationCode('');
      setRegistrationDebugCode(response.debug_code ?? null);
      setStep('verify');
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

  const handleVerifyRegistration = async () => {
    const email = normalizeEmail(registrationEmail);
    if (!email || registrationCode.length !== CODE_LENGTH) {
      toast.error('请输入完整验证码');
      return;
    }
    setIsSubmitting(true);
    try {
      await api.createRegistrationApplication({
        email,
        verification_channel: EMAIL_CHANNEL,
        verification_target: email,
        verification_code: registrationCode,
        organization_name: companyName.trim(),
        company_size: companySize,
        is_agency: isAgency,
        job_title: '体验申请',
      });
      setInviteCode('');
      setStep('invite');
      setCountdown(0);
      toast.success('登记已完成');
    } catch (error) {
      const message = error instanceof Error ? error.message : '登记失败';
      if (message.includes('已开通')) {
        setMode('login');
        setStep('login-email');
        setLoginEmail(email);
      }
      toast.error(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRedeemInvite = async () => {
    const email = normalizeEmail(registrationEmail);
    if (!email || inviteCode.length !== CODE_LENGTH) {
      toast.error('请输入完整邀请码');
      return;
    }
    setIsSubmitting(true);
    try {
      const response = await api.redeemInviteCode({
        email,
        invite_code: inviteCode,
      });
      setStoredAccessToken(response.access_token);
      toast.success('已进入工作台');
      router.replace(nextPath);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '邀请码验证失败');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSendLoginCode = async () => {
    const email = normalizeEmail(loginEmail);
    if (!email) {
      toast.error('请先输入邮箱地址');
      return;
    }
    setIsSendingCode(true);
    setLoginDebugCode(null);
    try {
      const response = await api.sendVerificationCode({
        channel: EMAIL_CHANNEL,
        purpose: 'login',
        target: email,
      });
      setCountdown(Math.max(30, Math.min(response.expires_in_seconds, 60)));
      setLoginCode('');
      setLoginDebugCode(response.debug_code ?? null);
      setStep('login-verify');
      toast.success(
        response.debug_code
          ? `登录验证码已生成，开发验证码：${response.debug_code}`
          : '登录验证码已发送'
      );
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '验证码发送失败');
    } finally {
      setIsSendingCode(false);
    }
  };

  const handleLogin = async () => {
    const email = normalizeEmail(loginEmail);
    if (!email || loginCode.length !== CODE_LENGTH) {
      toast.error('请输入完整验证码');
      return;
    }
    setIsSubmitting(true);
    try {
      const response = await api.loginWithOtp({
        channel: EMAIL_CHANNEL,
        target: email,
        verification_code: loginCode,
      });
      setStoredAccessToken(response.access_token);
      toast.success('登录成功');
      router.replace(nextPath);
    } catch (error) {
      const message = error instanceof Error ? error.message : '登录失败';
      if (message.includes('邀请码')) {
        setMode('apply');
        setRegistrationEmail(email);
        setStep('invite');
      }
      toast.error(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const renderApplyCompany = () => (
    <>
      <StepHeader
        mode="apply"
        step={1}
        title="介绍一下贵公司"
        description="这会帮助我们确认团队背景，并把邀请码发送到正确的邮箱。"
      />

      <div className="mt-12 max-w-[720px] space-y-10">
        <Field label="公司名称">
          <TextInput
            type="text"
            value={companyName}
            onChange={(event) => setCompanyName(event.target.value)}
            placeholder="输入公司名称"
          />
        </Field>

        <div>
          <div className="text-[17px] font-semibold text-[#111827]">贵公司的规模有多大？</div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {companySizeOptions.map((option) => (
              <OptionButton
                key={option}
                active={companySize === option}
                onClick={() => setCompanySize(option)}
              >
                {option}
              </OptionButton>
            ))}
          </div>
        </div>

        <label className="flex items-center gap-3 text-base font-medium text-[#111827]">
          <input
            type="checkbox"
            checked={isAgency}
            onChange={(event) => setIsAgency(event.target.checked)}
            className="h-5 w-5 rounded border border-[#d3d9e3]"
          />
          我是代理机构
        </label>

        <Field label="工作邮箱">
          <TextInput
            type="email"
            value={registrationEmail}
            onChange={(event) => setRegistrationEmail(event.target.value)}
            placeholder="you@company.com"
          />
        </Field>

        <PrimaryButton onClick={handleSendRegistrationCode} disabled={!canSendRegistrationCode}>
          {isSendingCode ? '发送中...' : '发送验证码'}
        </PrimaryButton>
      </div>
    </>
  );

  const renderApplyVerify = () => (
    <>
      <StepHeader
        mode="apply"
        step={2}
        title="验证你的邮箱"
        description={`验证码已发送至 ${maskEmail(registrationEmail)}`}
      />

      <div className="mt-12 max-w-[720px]">
        <CodeInputRow value={registrationCode} onChange={setRegistrationCode} />
        <div className="mt-6 flex items-center gap-3 text-sm text-[#6b7280]">
          <SecondaryAction
            onClick={handleSendRegistrationCode}
            disabled={!canSendRegistrationCode}
          >
            {isSendingCode
              ? '发送中...'
              : formatCountdown(countdown, '重新发送验证码')}
          </SecondaryAction>
        </div>
        {registrationDebugCode ? (
          <div className="mt-6 rounded-[20px] border border-[rgba(79,70,229,0.16)] bg-[rgba(79,70,229,0.06)] px-5 py-4 text-sm leading-7 text-[#4338ca]">
            <div className="font-semibold text-[#312e81]">开发环境验证码</div>
            <div className="mt-1">
              当前邮箱的验证码是 <span className="font-mono text-base font-semibold">{registrationDebugCode}</span>
            </div>
          </div>
        ) : null}
        <PrimaryButton
          className="mt-12"
          onClick={handleVerifyRegistration}
          disabled={isSubmitting || registrationCode.length !== CODE_LENGTH}
        >
          {isSubmitting ? '验证中...' : '继续'}
        </PrimaryButton>
      </div>
    </>
  );

  const renderApplyInvite = () => (
    <>
      <StepHeader
        mode="apply"
        step={3}
        title="输入邀请码"
        description="邀请码会发送至已登记邮箱。收到邀请码后，在这里输入即可进入平台。"
      />

      <div className="mt-10 grid max-w-[720px] gap-4">
        <InfoPanel
          icon={<RiMailLine className="h-5 w-5" />}
          title="邀请码发送邮箱"
          description={normalizeEmail(registrationEmail)}
        />
        <InfoPanel
          icon={<RiShieldKeyholeLine className="h-5 w-5" />}
          title="如何获得邀请码"
          description="我们会向已登记邮箱不定期发送邀请码。若暂未收到，请等待邮件通知或联系运营团队。"
        />
      </div>

      <div className="mt-12 max-w-[720px]">
        <CodeInputRow value={inviteCode} onChange={setInviteCode} />
        <PrimaryButton
          className="mt-12"
          onClick={handleRedeemInvite}
          disabled={isSubmitting || inviteCode.length !== CODE_LENGTH}
        >
          {isSubmitting ? '验证中...' : '验证邀请码'}
        </PrimaryButton>
      </div>
    </>
  );

  const renderLoginEmail = () => (
    <>
      <StepHeader
        mode="login"
        step={1}
        title="输入你的工作邮箱"
        description="输入已开通邮箱，我们会发送登录验证码。"
      />

      <div className="mt-12 max-w-[720px]">
        <Field label="邮箱">
          <TextInput
            type="email"
            value={loginEmail}
            onChange={(event) => setLoginEmail(event.target.value)}
            placeholder="you@company.com"
          />
        </Field>

        <PrimaryButton className="mt-12" onClick={handleSendLoginCode} disabled={!canSendLoginCode}>
          {isSendingCode ? '发送中...' : '发送登录验证码'}
        </PrimaryButton>
      </div>
    </>
  );

  const renderLoginVerify = () => (
    <>
      <StepHeader
        mode="login"
        step={2}
        title="验证你的邮箱"
        description={`登录验证码已发送至 ${maskEmail(loginEmail)}`}
      />

      <div className="mt-12 max-w-[720px]">
        <CodeInputRow value={loginCode} onChange={setLoginCode} />
        <div className="mt-6 flex items-center gap-3 text-sm text-[#6b7280]">
          <SecondaryAction onClick={handleSendLoginCode} disabled={!canSendLoginCode}>
            {isSendingCode
              ? '发送中...'
              : formatCountdown(countdown, '重新发送登录验证码')}
          </SecondaryAction>
        </div>
        {loginDebugCode ? (
          <div className="mt-6 rounded-[20px] border border-[rgba(79,70,229,0.16)] bg-[rgba(79,70,229,0.06)] px-5 py-4 text-sm leading-7 text-[#4338ca]">
            <div className="font-semibold text-[#312e81]">开发环境验证码</div>
            <div className="mt-1">
              当前邮箱的登录验证码是 <span className="font-mono text-base font-semibold">{loginDebugCode}</span>
            </div>
          </div>
        ) : null}
        <PrimaryButton
          className="mt-12"
          onClick={handleLogin}
          disabled={isSubmitting || loginCode.length !== CODE_LENGTH}
        >
          {isSubmitting ? '验证中...' : '登录'}
          <RiArrowRightLine className="ml-2 h-4 w-4" />
        </PrimaryButton>
      </div>
    </>
  );

  return (
    <main className="min-h-screen bg-[#fbfbf8] text-[#111827]">
      <div className="mx-auto max-w-[960px] px-6 py-8 lg:px-10 lg:py-10">
        <PageHeader mode={mode} onModeChange={changeMode} />

        <div className="mt-16">
          {mode === 'apply' && step === 'company' ? renderApplyCompany() : null}
          {mode === 'apply' && step === 'verify' ? renderApplyVerify() : null}
          {mode === 'apply' && step === 'invite' ? renderApplyInvite() : null}
          {mode === 'login' && step === 'login-email' ? renderLoginEmail() : null}
          {mode === 'login' && step === 'login-verify' ? renderLoginVerify() : null}
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
