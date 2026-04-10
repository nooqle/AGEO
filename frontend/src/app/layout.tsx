import type { Metadata } from 'next';
import './globals.css';
import '@/styles/design-system.css';
import { ToastContainer } from '@/components/ui/toast';
import { SiteFooter } from '@/components/layout/SiteFooter';

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
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('specta-theme');if(t==='light'){document.documentElement.setAttribute('data-theme','light');}}catch(e){}})();`,
          }}
        />
      </head>
      <body className="antialiased">
        {children}
        <SiteFooter />
        <ToastContainer />
      </body>
    </html>
  );
}
