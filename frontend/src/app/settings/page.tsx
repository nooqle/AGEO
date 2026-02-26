'use client';

import Link from 'next/link';
import { DashboardTopBar } from '@/components/layout/DashboardTopBar';
import {
  RiKey2Line,
  RiNotification3Line,
  RiTeamLine,
  RiDatabase2Line,
  RiArrowLeftLine,
} from '@remixicon/react';

const SETTINGS_ITEMS = [
  {
    icon: RiKey2Line,
    title: 'API 密钥管理',
    description: '管理 LLM 和第三方服务的 API 密钥配置',
  },
  {
    icon: RiNotification3Line,
    title: '通知偏好',
    description: '配置分析完成、异常告警等通知方式',
  },
  {
    icon: RiTeamLine,
    title: '团队管理',
    description: '邀请团队成员、分配角色与权限',
  },
  {
    icon: RiDatabase2Line,
    title: '数据导出设置',
    description: '配置自动导出格式、存储位置和调度规则',
  },
];

export default function Settings() {
  return (
    <div className="h-screen flex flex-col" style={{ backgroundColor: 'var(--bg-primary)' }}>
      <DashboardTopBar />
      <div className="flex-1 overflow-y-auto p-8">
        <div className="max-w-2xl mx-auto">
          {/* Header */}
          <div className="mb-8">
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-1.5 text-sm mb-4 transition-colors"
              style={{ color: 'var(--text-tertiary)' }}
            >
              <RiArrowLeftLine className="w-4 h-4" />
              返回控制台
            </Link>
            <h1 className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
              设置
            </h1>
            <p className="text-sm mt-1" style={{ color: 'var(--text-tertiary)' }}>
              以下功能正在开发中，敬请期待
            </p>
          </div>

          {/* Settings cards */}
          <div className="grid gap-4">
            {SETTINGS_ITEMS.map((item) => (
              <div
                key={item.title}
                className="flex items-start gap-4 p-5 rounded-xl opacity-60 cursor-not-allowed"
                style={{
                  backgroundColor: 'var(--bg-secondary)',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                <div
                  className="p-2.5 rounded-lg flex-shrink-0"
                  style={{
                    backgroundColor: 'var(--bg-elevated)',
                    border: '1px solid var(--border-subtle)',
                  }}
                >
                  <item.icon className="w-5 h-5" style={{ color: 'var(--text-tertiary)' }} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                      {item.title}
                    </h3>
                    <span
                      className="text-xs px-2 py-0.5 rounded-full"
                      style={{
                        backgroundColor: 'var(--bg-elevated)',
                        color: 'var(--text-tertiary)',
                        border: '1px solid var(--border-subtle)',
                      }}
                    >
                      即将推出
                    </span>
                  </div>
                  <p className="text-xs mt-1" style={{ color: 'var(--text-tertiary)' }}>
                    {item.description}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
