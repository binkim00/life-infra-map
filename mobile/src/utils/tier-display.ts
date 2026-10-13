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
  tier_color?: string;
  nickname_color?: string;
};

const TIER_COLORS: Record<string, string> = {
  iron: "#8b8b8b", bronze: "#b7791f", silver: "#9ca3af", gold: "#f59e0b",
  platinum: "#14b8a6", diamond: "#3b82f6", master: "#8b5cf6", challenger: "#ef4444",
};

export const tierColor = (user: TierUser | null | undefined) => {
  const nested = typeof user?.tier === "object" ? user.tier : undefined;
  const supplied = user?.tier_color || user?.nickname_color || nested?.tier_color || nested?.nickname_color;
  if (typeof supplied === "string" && /^#[0-9a-f]{6}$/i.test(supplied)) return supplied.toLowerCase();
  const code = typeof user?.tier === "string" ? user.tier : String(nested?.tier || "");
  return TIER_COLORS[code] || TIER_COLORS.iron;
};

export type AuthorTierData = { author_tier?: string; author_tier_label?: string; author_nickname_color?: string };
export const authorTierDisplay = (author: AuthorTierData) => ({
  label: tierDisplay({ tier: author.author_tier, tier_label: author.author_tier_label }).label,
  color: tierColor({ tier: author.author_tier, nickname_color: author.author_nickname_color }),
});

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
