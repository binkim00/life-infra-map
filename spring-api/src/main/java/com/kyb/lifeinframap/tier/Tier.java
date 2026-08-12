package com.kyb.lifeinframap.tier;

/**
 * 기여도에 따른 등급입니다. Django `accounts/utils.py` 의 TIER_RULES 와 값을 맞춰야 합니다.
 *
 * 한쪽만 바꾸면 화면에 서로 다른 배지가 뜹니다.
 */
public enum Tier {

    CHALLENGER(1000, "challenger", "챌린저", "#ef4444"),
    MASTER(700, "master", "마스터", "#8b5cf6"),
    DIAMOND(500, "diamond", "다이아", "#3b82f6"),
    PLATINUM(300, "platinum", "플래티넘", "#14b8a6"),
    GOLD(200, "gold", "골드", "#f59e0b"),
    SILVER(100, "silver", "실버", "#9ca3af"),
    BRONZE(50, "bronze", "브론즈", "#b7791f"),
    IRON(0, "iron", "아이언", "#8b8b8b");

    private final int minimumScore;
    private final String code;
    private final String label;
    private final String color;

    Tier(int minimumScore, String code, String label, String color) {
        this.minimumScore = minimumScore;
        this.code = code;
        this.label = label;
        this.color = color;
    }

    /** 선언 순서가 점수 내림차순이므로 위에서부터 처음 만족하는 등급을 씁니다. */
    public static Tier byScore(int score) {
        for (Tier tier : values()) {
            if (score >= tier.minimumScore) {
                return tier;
            }
        }
        return IRON;
    }

    public String getCode() {
        return code;
    }

    public String getLabel() {
        return label;
    }

    public String getColor() {
        return color;
    }
}
