export default function ChatLoading() {
  return (
    <div className="h-screen flex items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <div className="w-12 h-12 rounded-full border-4 border-[var(--border-subtle)] border-t-[var(--brand-primary)] animate-spin" />
        <p className="text-[var(--text-secondary)]">加载中...</p>
      </div>
    </div>
  );
}
