// CitationCard.tsx – expandable card showing one citation with trust badge.

"use client";

import { useState } from "react";
import type { Citation } from "@/lib/types";
import { TrustBadge } from "./TrustBadge";

interface CitationCardProps {
  citation: Citation;
  index: number;
}

export function CitationCard({ citation, index }: CitationCardProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-gray-200 rounded-lg p-3 text-sm space-y-1">
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-semibold text-gray-500">[{index}]</span>
          <TrustBadge tier={citation.trust_tier} score={citation.trust_score} />
          <span className="text-xs text-gray-500 uppercase">{citation.source}</span>
        </div>
        <button
          onClick={() => setExpanded((e) => !e)}
          className="text-xs text-blue-600 hover:underline shrink-0"
        >
          {expanded ? "Less" : "More"}
        </button>
      </div>

      {/* Title and link */}
      <p className="font-medium text-gray-800">
        {citation.url ? (
          <a
            href={citation.url}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:underline text-blue-700"
          >
            {citation.title}
          </a>
        ) : (
          citation.title
        )}
      </p>

      {/* Excerpt – always shown */}
      <p className="text-gray-600 text-xs italic line-clamp-2">{citation.excerpt}</p>

      {/* Expanded details */}
      {expanded && (
        <div className="mt-2 space-y-1 text-xs text-gray-500">
          {citation.authors && <p><strong>Authors:</strong> {citation.authors}</p>}
          {citation.journal && <p><strong>Journal:</strong> {citation.journal}</p>}
          {citation.published_at && (
            <p><strong>Published:</strong> {citation.published_at.slice(0, 10)}</p>
          )}
          {citation.doi && (
            <p>
              <strong>DOI:</strong>{" "}
              <a
                href={`https://doi.org/${citation.doi}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 hover:underline"
              >
                {citation.doi}
              </a>
            </p>
          )}
        </div>
      )}
    </div>
  );
}
