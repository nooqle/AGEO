import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { chromium } from 'playwright-core';

function findExecutableInDir(root: string): string | null {
  if (!fs.existsSync(root)) {
    return null;
  }

  let candidates: fs.Dirent[];
  try {
    candidates = fs.readdirSync(root, { withFileTypes: true })
      .filter((entry) => entry.isDirectory() && entry.name.startsWith('chromium'))
      .sort((a, b) => b.name.localeCompare(a.name, 'en'));
  } catch {
    return null;
  }

  for (const entry of candidates) {
    const base = path.join(/*turbopackIgnore: true*/ root, entry.name);
    const possibleFiles = [
      path.join(/*turbopackIgnore: true*/ base, 'chrome-win', 'chrome.exe'),
      path.join(/*turbopackIgnore: true*/ base, 'chrome-win64', 'chrome.exe'),
      path.join(/*turbopackIgnore: true*/ base, 'chrome-linux', 'chrome'),
      path.join(/*turbopackIgnore: true*/ base, 'chrome-mac', 'Chromium.app', 'Contents', 'MacOS', 'Chromium'),
    ];

    for (const file of possibleFiles) {
      if (fs.existsSync(file)) {
        return file;
      }
    }
  }

  return null;
}

function findChromiumExecutable(): string | null {
  const envCandidates = [
    process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
    process.env.CHROME_EXECUTABLE_PATH,
  ].filter((value): value is string => Boolean(value));

  for (const file of envCandidates) {
    if (fs.existsSync(file)) {
      return file;
    }
  }

  const systemCandidates = process.platform === 'win32'
    ? [
        'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
      ]
    : [
        '/usr/bin/google-chrome-stable',
        '/usr/bin/google-chrome',
        '/usr/bin/microsoft-edge',
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
      ];

  for (const file of systemCandidates) {
    if (fs.existsSync(file)) {
      return file;
    }
  }

  const home = os.homedir();
  const playwrightRoots = process.platform === 'win32'
    ? [path.join(/*turbopackIgnore: true*/ home, 'AppData', 'Local', 'ms-playwright')]
    : [path.join(/*turbopackIgnore: true*/ home, '.cache', 'ms-playwright')];

  for (const root of playwrightRoots) {
    const found = findExecutableInDir(root);
    if (found) {
      return found;
    }
  }

  return null;
}

export async function launchPdfBrowser() {
  const executablePath = findChromiumExecutable();
  try {
    return await chromium.launch({
      headless: true,
      ...(executablePath ? { executablePath } : {}),
      args: ['--font-render-hinting=medium'],
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (
      process.platform === 'linux'
      && /libatk-1\.0\.so\.0|error while loading shared libraries/i.test(message)
    ) {
      throw new Error(
        'PDF 导出环境缺少 Chromium 运行库（例如 libatk-1.0.so.0），请先安装 Playwright Linux 依赖后再重试。'
      );
    }
    throw error;
  }
}
