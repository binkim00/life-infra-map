package com.kyb.lifeinframap;

import static org.assertj.core.api.Assertions.assertThat;

import com.kyb.lifeinframap.tier.domain.ContributionRules;
import com.kyb.lifeinframap.tier.domain.Tier;
import java.util.Map;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** Django accounts/utils.py 와 계산 결과가 같아야 합니다. */
class ContributionRulesTest {

    @Test
    @DisplayName("글은 5개당 1점, 댓글은 10개당 1점으로 올림 계산한다")
    void groupsActivityCounts() {
        assertThat(ContributionRules.groupCount(0, 5)).isZero();
        assertThat(ContributionRules.groupCount(1, 5)).isEqualTo(1);
        assertThat(ContributionRules.groupCount(5, 5)).isEqualTo(1);
        assertThat(ContributionRules.groupCount(6, 5)).isEqualTo(2);
        assertThat(ContributionRules.groupCount(11, 10)).isEqualTo(2);
    }

    @Test
    @DisplayName("하루 활동 기여도는 상한 5점을 넘지 않는다")
    void capsDailyActivity() {
        assertThat(ContributionRules.dailyActivity(0, 0)).isZero();
        assertThat(ContributionRules.dailyActivity(1, 0)).isEqualTo(1);
        assertThat(ContributionRules.dailyActivity(5, 10)).isEqualTo(2);
        // 글 50개(10점) + 댓글 100개(10점) = 20점이지만 상한 5점
        assertThat(ContributionRules.dailyActivity(50, 100)).isEqualTo(5);
    }

    @Test
    @DisplayName("승인된 제보 유형별 점수를 합산한다")
    void sumsReportRewards() {
        assertThat(ContributionRules.reportContribution(Map.of("new_place", 2L))).isEqualTo(40);
        assertThat(ContributionRules.reportContribution(
                Map.of("tag_suggestion", 1L, "wrong_info", 2L, "edit_place", 1L))).isEqualTo(25);
        // 알 수 없는 유형은 0점입니다.
        assertThat(ContributionRules.reportContribution(Map.of("unknown_type", 5L))).isZero();
        assertThat(ContributionRules.reportContribution(null)).isZero();
    }

    @Test
    @DisplayName("점수 구간마다 등급이 갈린다")
    void mapsScoreToTier() {
        assertThat(Tier.byScore(0).getCode()).isEqualTo("iron");
        assertThat(Tier.byScore(49).getCode()).isEqualTo("iron");
        assertThat(Tier.byScore(50).getCode()).isEqualTo("bronze");
        assertThat(Tier.byScore(100).getCode()).isEqualTo("silver");
        assertThat(Tier.byScore(200).getCode()).isEqualTo("gold");
        assertThat(Tier.byScore(300).getCode()).isEqualTo("platinum");
        assertThat(Tier.byScore(500).getCode()).isEqualTo("diamond");
        assertThat(Tier.byScore(700).getCode()).isEqualTo("master");
        assertThat(Tier.byScore(1000).getCode()).isEqualTo("challenger");
        assertThat(Tier.byScore(99999).getCode()).isEqualTo("challenger");
    }

    @Test
    @DisplayName("등급 이름과 색이 Django 값과 같다")
    void keepsLabelsAndColors() {
        assertThat(Tier.IRON.getLabel()).isEqualTo("아이언");
        assertThat(Tier.CHALLENGER.getLabel()).isEqualTo("챌린저");
        assertThat(Tier.GOLD.getColor()).isEqualTo("#f59e0b");
        assertThat(Tier.IRON.getColor()).isEqualTo("#8b8b8b");
    }
}
