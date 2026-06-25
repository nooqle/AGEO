export function triggerBrowserDownload(blob: Blob, filename: string) {
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return false;
  }
  if (!blob || blob.size === 0) {
    return false;
  }

  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename || 'download';
  anchor.rel = 'noopener';
  anchor.style.display = 'none';
  document.body.appendChild(anchor);
  anchor.click();

  window.setTimeout(() => {
    anchor.remove();
    window.URL.revokeObjectURL(url);
  }, 60_000);

  return true;
}
