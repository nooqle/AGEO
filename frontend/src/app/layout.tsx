import type { Metadata } from 'next';
import './globals.css';
import '@/styles/design-system.css';
import { ToastContainer } from '@/components/ui/toast';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { ThemeBootstrap } from '@/components/layout/ThemeBootstrap';

export const metadata: Metadata = {
  title: 'Specta AI - 品牌声量智能分析平台',
  description: 'Specta AI - 品牌声量智能分析',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body className="antialiased">
        <ThemeBootstrap />
        {children}
        <SiteFooter />
        <ToastContainer />
      </body>
    </html>
  );
}
