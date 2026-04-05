import { ReportContent } from './ReportContent';
import { ConfidenceSignalContent } from './ConfidenceSignalContent';
import { FetchResultsContent } from './FetchResultsContent';
import { DataTableContent } from './DataTableContent';
import { PrintReady } from './PrintReady';
import { isConfidenceCanvasReport } from '@/adapters/exportArtifacts';
import type { CanvasContent } from '@/types/canvas';

export function PrintCanvasContent({ content }: { content: CanvasContent }) {
  return (
    <>
      <PrintReady />
      {content.type === 'fetchResults' ? (
        <FetchResultsContent content={content} printMode />
      ) : content.type === 'dataTable' ? (
        <DataTableContent content={content} />
      ) : content.type === 'report' && isConfidenceCanvasReport(content) ? (
        <ConfidenceSignalContent content={content} printMode />
      ) : content.type === 'report' ? (
        <ReportContent content={content} printMode />
      ) : null}
    </>
  );
}
