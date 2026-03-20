import { promises as fs } from 'node:fs';

export const runtime = 'nodejs';

const FONT_PATH = 'C:\\Windows\\Fonts\\simhei.ttf';

export async function GET() {
  try {
    const font = await fs.readFile(FONT_PATH);
    return new Response(font, {
      headers: {
        'Content-Type': 'font/ttf',
        'Cache-Control': 'public, max-age=31536000, immutable',
      },
    });
  } catch {
    return new Response('Font not found', { status: 404 });
  }
}
