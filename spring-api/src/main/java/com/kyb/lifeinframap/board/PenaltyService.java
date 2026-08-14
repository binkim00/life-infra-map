package com.kyb.lifeinframap.board;

import com.kyb.lifeinframap.account.User;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 활동정지/밴 확인입니다.
 *
 * 기존 Django 구현과 동일한 제재 판정 및 응답 계약을 제공합니다.
 * 글쓰기·댓글·좋아요·신고처럼 쓰기 동작 앞에서 확인합니다.
 */
@Service
public class PenaltyService {

    private final UserPenaltyRepository penaltyRepository;

    public PenaltyService(UserPenaltyRepository penaltyRepository) {
        this.penaltyRepository = penaltyRepository;
    }

    /** 유효한 제재가 있으면 돌려줍니다. 기간이 지난 제재는 무시합니다. */
    @Transactional(readOnly = true)
    public UserPenalty findCurrent(Integer userId) {
        List<UserPenalty> penalties = penaltyRepository.findEffective(userId, OffsetDateTime.now());
        return penalties.isEmpty() ? null : penalties.get(0);
    }

    public boolean isBlocked(User user) {
        return user != null && findCurrent(user.getId()) != null;
    }

    /** Django 응답 형태를 그대로 맞춥니다. 프론트가 이 필드들을 읽습니다. */
    public Map<String, Object> serialize(UserPenalty penalty) {
        Map<String, Object> payload = new LinkedHashMap<>();
        if (penalty == null) {
            payload.put("is_suspended", false);
            payload.put("suspended_until", null);
            payload.put("is_permanent_ban", false);
            payload.put("reason", "");
            payload.put("penalty_type", "");
            return payload;
        }
        payload.put("is_suspended", true);
        payload.put("suspended_until", penalty.getEndAt());
        payload.put("is_permanent_ban", "permanent_ban".equals(penalty.getPenaltyType()));
        payload.put("reason", penalty.getReason());
        payload.put("penalty_type", penalty.getPenaltyType());
        return payload;
    }

    public Map<String, Object> blockedBody(UserPenalty penalty) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("detail", "현재 활동정지 또는 밴 상태라 이 작업을 할 수 없습니다.");
        body.put("penalty", serialize(penalty));
        return body;
    }
}
