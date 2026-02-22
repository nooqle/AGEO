'use client';

import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface MarkdownContentProps {
  content: string;
  className?: string;
}

const REMARK_PLUGINS = [remarkGfm];

const MARKDOWN_COMPONENTS = {
  h1: ({ children }: { children: React.ReactNode }) => (
    <h1 className="text-xl font-bold mt-5 mb-3 first:mt-0" style={{ color: 'var(--text-primary)' }}>
      {children}
    </h1>
  ),
  h2: ({ children }: { children: React.ReactNode }) => (
    <h2 className="text-lg font-semibold mt-4 mb-2 first:mt-0" style={{ color: 'var(--text-primary)' }}>
      {children}
    </h2>
  ),
  h3: ({ children }: { children: React.ReactNode }) => (
    <h3 className="text-base font-medium mt-3 mb-1.5 first:mt-0" style={{ color: 'var(--text-primary)' }}>
      {children}
    </h3>
  ),
  p: ({ children }: { children: React.ReactNode }) => (
    <p className="text-[15px] leading-normal mb-2 last:mb-0" style={{ color: 'var(--text-primary)' }}>
      {children}
    </p>
  ),
  strong: ({ children }: { children: React.ReactNode }) => (
    <strong className="font-semibold" style={{ color: 'var(--text-primary)' }}>
      {children}
    </strong>
  ),
  em: ({ children }: { children: React.ReactNode }) => (
    <em className="italic" style={{ color: 'var(--text-secondary)' }}>
      {children}
    </em>
  ),
  ul: ({ children }: { children: React.ReactNode }) => (
    <ul className="list-disc list-inside text-[15px] mb-2 space-y-1 pl-1" style={{ color: 'var(--text-primary)' }}>
      {children}
    </ul>
  ),
  ol: ({ children }: { children: React.ReactNode }) => (
    <ol className="list-decimal list-inside text-[15px] mb-2 space-y-1 pl-1" style={{ color: 'var(--text-primary)' }}>
      {children}
    </ol>
  ),
  li: ({ children }: { children: React.ReactNode }) => (
    <li className="text-[15px] leading-normal" style={{ color: 'var(--text-primary)' }}>
      {children}
    </li>
  ),
  pre: ({ children }: { children: React.ReactNode }) => (
    <pre className="rounded-lg p-3 my-3 overflow-x-auto" style={{
      background: 'var(--bg-tertiary)',
      border: '1px solid var(--border-default)',
    }}>
      {children}
    </pre>
  ),
  code: ({ children, className }: { children: React.ReactNode; className?: string }) => {
    const isBlock = !!className;
    return isBlock ? (
      <code className={`text-[13px] font-mono ${className || ''}`} style={{ color: 'var(--text-tertiary)' }}>
        {children}
      </code>
    ) : (
      <code className="px-1.5 py-0.5 rounded text-[13px] font-mono" style={{
        background: 'var(--bg-elevated)',
        color: 'var(--text-tertiary)',
      }}>
        {children}
      </code>
    );
  },
  blockquote: ({ children }: { children: React.ReactNode }) => (
    <blockquote className="border-l-2 pl-3 my-3 italic" style={{
      borderColor: 'var(--color-primary)',
      color: 'var(--text-tertiary)',
    }}>
      {children}
    </blockquote>
  ),
  a: ({ children, href }: { children: React.ReactNode; href?: string }) => (
    <a
      href={href}
      className="underline transition-colors"
      style={{ color: 'var(--color-primary)' }}
      target="_blank"
      rel="noopener noreferrer"
    >
      {children}
    </a>
  ),
  hr: () => (
    <hr className="my-4" style={{ borderColor: 'var(--border-default)' }} />
  ),
  table: ({ children }: { children: React.ReactNode }) => (
    <div className="overflow-x-auto my-3 rounded-lg" style={{ border: '1px solid var(--border-default)' }}>
      <table className="w-full text-[15px] border-collapse min-w-[400px]" style={{ color: 'var(--text-primary)' }}>
        {children}
      </table>
    </div>
  ),
  thead: ({ children }: { children: React.ReactNode }) => (
    <thead style={{ background: 'var(--bg-elevated)', borderBottom: '1px solid var(--border-default)' }}>
      {children}
    </thead>
  ),
  tbody: ({ children }: { children: React.ReactNode }) => (
    <tbody>
      {children}
    </tbody>
  ),
  tr: ({ children }: { children: React.ReactNode }) => (
    <tr className="hover-bg-elevated transition-colors" style={{ borderBottom: '1px solid var(--border-default)' }}>
      {children}
    </tr>
  ),
  th: ({ children }: { children: React.ReactNode }) => (
    <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider" style={{
      color: 'var(--text-tertiary)',
      borderRight: '1px solid var(--border-default)',
    }}>
      {children}
    </th>
  ),
  td: ({ children }: { children: React.ReactNode }) => (
    <td className="px-3 py-2 text-[15px]" style={{
      color: 'var(--text-primary)',
      borderRight: '1px solid var(--border-default)',
    }}>
      {children}
    </td>
  ),
} as unknown as Record<string, React.ComponentType<Record<string, unknown>>>;

export const MarkdownContent = React.memo(function MarkdownContent({
  content,
  className = '',
}: MarkdownContentProps) {
  return (
    <div className={`markdown-content ${className}`}>
      <ReactMarkdown
        remarkPlugins={REMARK_PLUGINS}
        components={MARKDOWN_COMPONENTS}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
});
