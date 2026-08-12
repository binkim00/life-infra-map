package com.kyb.lifeinframap.tier;

import java.util.Map;

/**
 * 기여도 계산 규칙입니다. Django `accounts/utils.py` 와 값을 맞춰야 합니다.
 *
 * 계산식만 담고 DB 는 건드리지 않아 단위 테스트로 검증할 수 있습니다.
 */
public final class ContributionRules {

    public static final int POSTS_PER_POINT = 5;
    public static final int COMMENTS_PER_POINT = 10;
    public static final int DAILY_LIMIT = 5;
    public static final int STAFF_DEMO_BASE = 6;

    public static final Map<String, Integer> REPORT_REWARDS = Map.of(
            "tag_suggestion", 10,
            "wrong_info", 5,
            "edit_place", 5,
            "new_place", 20);

    private ContributionRules() {
    }

    /** 글 5개당 1점처럼 묶음 단위로 올림 계산합니다. */
    public static int groupCount(int count, int groupSize) {
        if (count <= 0) {
            return 0;
        }
        return (count + groupSize - 1) / groupSize;
    }

    /** 하루치 활동 기여도입니다. 상한을 넘지 않습니다. */
    public static int dailyActivity(int postCount, int commentCount) {
        int raw = groupCount(postCount, POSTS_PER_POINT) + groupCount(commentCount, COMMENTS_PER_POINT);
        return Math.min(DAILY_LIMIT, raw);
    }

    /** 승인된 제보 기여도입니다. 알 수 없는 유형은 0점입니다. */
    public static int reportContribution(Map<String, Long> approvedReportCounts) {
        if (approvedReportCounts == null) {
            return 0;
        }
        int total = 0;
        for (Map.Entry<String, Long> entry : approvedReportCounts.entrySet()) {
            total += REPORT_REWARDS.getOrDefault(entry.getKey(), 0) * entry.getValue().intValue();
        }
        return total;
    }
}
