// TrustBadge.tsx – displays a colored badge for trust tier A/B/C.

interface TrustBadgeProps {
  tier: "A" | "B" | "C";
  score: number;
}

const TIER_STYLES = {
  A: "bg-green-100 text-green-800 border-green-300",
  B: "bg-amber-100 text-amber-800 border-amber-300",
  C: "bg-red-100 text-red-800 border-red-300",
};

const TIER_LABELS = {
  A: "High trust",
  B: "Moderate trust",
  C: "Lower trust",
};

export function TrustBadge({ tier, score }: TrustBadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded border ${TIER_STYLES[tier]}`}
      title={`${TIER_LABELS[tier]} (score: ${score.toFixed(2)})`}
    >
      Tier {tier}
    </span>
  );
}
