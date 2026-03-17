import { ReportContent } from './ReportContent';
import { ConfidenceSignalContent } from './ConfidenceSignalContent';
import { FetchResultsContent } from './FetchResultsContent';
import { PrintReady } from './PrintReady';
import type { CanvasContent } from '@/types/canvas';

export function PrintCanvasContent({ content }: { content: CanvasContent }) {
  return (
    <>
      <PrintReady />
      {content.type === 'fetchResults' ? (
        <FetchResultsContent content={content} printMode />
      ) : content.type === 'report' && (content.data.report_kind === 'confidence_signal' || content.data.artifact_kind === 'confidence_signal') ? (
        <ConfidenceSignalContent content={content} printMode />
      ) : content.type === 'report' ? (
        <ReportContent content={content} printMode />
      ) : null}
    </>
  );
}
