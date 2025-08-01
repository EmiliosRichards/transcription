"use client";

interface SourceDocument {
  customer_id: string;
  full_journey: string;
  call_ids: string;
  distance: number;
}

interface SourceDocumentsProps {
  sourceDocuments: SourceDocument[];
  onSourceClick: (source: SourceDocument) => void;
}

export function SourceDocuments({ sourceDocuments, onSourceClick }: SourceDocumentsProps) {
  if (!sourceDocuments || sourceDocuments.length === 0) {
    return null;
  }

  return (
    <div>
      <details>
        <summary className="text-sm font-semibold cursor-pointer">
          View Sources ({sourceDocuments.length})
        </summary>
        <div className="mt-2 space-y-2">
          {sourceDocuments.map((doc) => (
            <div key={doc.customer_id} className="p-2 border rounded bg-background/50 cursor-pointer hover:bg-muted" onClick={() => onSourceClick(doc)}>
              <p className="text-sm font-bold">Customer ID: {doc.customer_id}</p>
              <p className="text-xs text-muted-foreground">Call IDs: {doc.call_ids}</p>
              <p className="text-sm mt-1 italic">"{doc.full_journey.substring(0, 200)}..."</p>
            </div>
          ))}
        </div>
      </details>
    </div>
  );
}