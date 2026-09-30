const TIER_LABELS: Record<string, string> = {
  iron: "아이언", bronze: "브론즈", silver: "실버", gold: "골드",
  platinum: "플래티넘", diamond: "다이아", master: "마스터",
  challenger: "챌린저",
};

type TierUser = {
  tier?: string | Record<string, unknown>;
  tier_label?: string;
  contribution?: number;
  score?: number;
};

export const tierDisplay = (user: TierUser | null | undefined) => {
  if (!user) return { label: "등급 확인 중", contribution: null };
  const code = typeof user.tier === "string" ? user.tier :
    typeof user.tier?.tier === "string" ? user.tier.tier : "";
  const label = TIER_LABELS[code] || user.tier_label || "등급 확인 중";
  const score = user.contribution ?? user.score;
  return {
    label,
    contribution: typeof score === "number" && Number.isFinite(score) ? score : null,
  };
};
