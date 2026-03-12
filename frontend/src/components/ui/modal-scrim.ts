import { cn } from '@/lib/cn';

export const MODAL_SCRIM_BASE_CLASSNAME =
  'fixed inset-0 bg-[rgba(15,18,28,0.34)] supports-[backdrop-filter]:bg-[rgba(15,18,28,0.24)] backdrop-blur-[16px]';

export function modalScrimClassName(...classNames: Array<string | false | null | undefined>) {
  return cn(MODAL_SCRIM_BASE_CLASSNAME, ...classNames);
}
