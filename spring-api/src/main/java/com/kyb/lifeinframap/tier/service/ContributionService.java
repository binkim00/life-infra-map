package com.kyb.lifeinframap.tier.service;

import com.kyb.lifeinframap.tier.domain.*;
import com.kyb.lifeinframap.tier.service.*;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 사용자 기여도와 등급을 계산합니다.
 *
 * 게시판 활동(boards)과 승인된 장소 제보(recommendations)를 함께 봅니다.
 * 두 데이터가 모두 Spring 쪽으로 오기 때문에 여기서 자기 완결로 계산할 수 있습니다.
 *
 * 계산 규칙은 Django `accounts/utils.py` 와 같아야 합니다.
 * 날짜별 묶음이 필요해 JPQL 대신 네이티브 질의를 씁니다.
 */
@Service
public class ContributionService {

    @PersistenceContext
    private EntityManager entityManager;

    public record TierInfo(int score, int contribution, String tier, String tierLabel,
                           String tierColor, String nicknameColor) {
    }

    /**
     * 여러 사용자의 등급을 한 번에 계산합니다.
     *
     * 게시글 목록처럼 작성자가 여러 명인 화면에서 한 명씩 조회하면 N+1 이 됩니다.
     */
    @Transactional(readOnly = true)
    public Map<Integer, TierInfo> getTierInfo(List<Integer> userIds, Set<Integer> staffUserIds) {
        Map<Integer, TierInfo> result = new LinkedHashMap<>();
        if (userIds == null || userIds.isEmpty()) {
            return result;
        }
        List<Integer> ids = new ArrayList<>(new HashSet<>(userIds));

        Map<Integer, Integer> activity = dailyActivityContribution(ids);
        Map<Integer, Integer> reports = approvedReportContribution(ids);

        for (Integer userId : ids) {
            int contribution = activity.getOrDefault(userId, 0)
                    + reports.getOrDefault(userId, 0)
                    + (staffUserIds != null && staffUserIds.contains(userId)
                            ? ContributionRules.STAFF_DEMO_BASE : 0);
            Tier tier = Tier.byScore(contribution);
            result.put(userId, new TierInfo(
                    contribution, contribution, tier.getCode(), tier.getLabel(),
                    tier.getColor(), tier.getColor()));
        }
        return result;
    }

    @Transactional(readOnly = true)
    public TierInfo getTierInfo(Integer userId, boolean staff) {
        return getTierInfo(List.of(userId), staff ? Set.of(userId) : Set.of())
                .getOrDefault(userId, new TierInfo(0, 0, Tier.IRON.getCode(),
                        Tier.IRON.getLabel(), Tier.IRON.getColor(), Tier.IRON.getColor()));
    }

    /**
     * 날짜별 글/댓글 수를 세어 하루 상한을 적용한 뒤 합칩니다.
     *
     * Django 는 `TruncDate` 로 서버 시간대 기준 날짜를 씁니다. 같은 기준을 쓰기 위해
     * `created_at` 을 date 로 캐스팅합니다.
     */
    private Map<Integer, Integer> dailyActivityContribution(List<Integer> userIds) {
        Map<Integer, Map<Object, int[]>> byUser = new HashMap<>();

        collectDailyCounts(
                "select author_id, created_at::date as d, count(*) from boards_post "
                        + "where author_id in (:ids) group by author_id, d",
                userIds, byUser, 0);
        collectDailyCounts(
                "select author_id, created_at::date as d, count(*) from boards_comment "
                        + "where author_id in (:ids) group by author_id, d",
                userIds, byUser, 1);

        Map<Integer, Integer> result = new HashMap<>();
        for (Map.Entry<Integer, Map<Object, int[]>> entry : byUser.entrySet()) {
            int total = 0;
            for (int[] counts : entry.getValue().values()) {
                total += ContributionRules.dailyActivity(counts[0], counts[1]);
            }
            result.put(entry.getKey(), total);
        }
        return result;
    }

    @SuppressWarnings("unchecked")
    private void collectDailyCounts(String sql, List<Integer> userIds,
                                    Map<Integer, Map<Object, int[]>> byUser, int slot) {
        List<Object[]> rows = entityManager.createNativeQuery(sql)
                .setParameter("ids", userIds)
                .getResultList();
        for (Object[] row : rows) {
            Integer userId = ((Number) row[0]).intValue();
            Object date = row[1];
            int count = ((Number) row[2]).intValue();
            byUser.computeIfAbsent(userId, key -> new HashMap<>())
                    .computeIfAbsent(date, key -> new int[2])[slot] = count;
        }
    }

    /** 승인된 제보 유형별 개수를 점수로 바꿉니다. */
    @SuppressWarnings("unchecked")
    private Map<Integer, Integer> approvedReportContribution(List<Integer> userIds) {
        List<Object[]> rows = entityManager.createNativeQuery(
                        "select user_id, report_type, count(*) from recommendations_placereport "
                                + "where status = 'approved' and user_id in (:ids) "
                                + "group by user_id, report_type")
                .setParameter("ids", userIds)
                .getResultList();

        Map<Integer, Map<String, Long>> byUser = new HashMap<>();
        for (Object[] row : rows) {
            Integer userId = ((Number) row[0]).intValue();
            byUser.computeIfAbsent(userId, key -> new HashMap<>())
                    .put((String) row[1], ((Number) row[2]).longValue());
        }

        Map<Integer, Integer> result = new HashMap<>();
        byUser.forEach((userId, counts) -> result.put(userId, ContributionRules.reportContribution(counts)));
        return result;
    }
}
