package com.kyb.lifeinframap.board.domain;

import com.kyb.lifeinframap.board.domain.*;
import com.kyb.lifeinframap.board.repository.*;
import com.kyb.lifeinframap.board.service.*;
import com.kyb.lifeinframap.board.dto.*;

import com.kyb.lifeinframap.account.domain.User;
import jakarta.persistence.*;
import java.time.OffsetDateTime;

/** Django `boards_userpenalty` 매핑. 활동정지/밴 이력입니다. */
@Entity
@Table(name = "boards_userpenalty")
public class UserPenalty {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @Column(name = "penalty_type", nullable = false, length = 30)
    private String penaltyType;

    @Column(nullable = false, columnDefinition = "text")
    private String reason;

    @Column(name = "start_at", nullable = false)
    private OffsetDateTime startAt;

    /** 비어 있으면 영구 제재입니다. */
    @Column(name = "end_at")
    private OffsetDateTime endAt;

    @Column(name = "is_active", nullable = false)
    private boolean active;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "created_by_id")
    private User createdBy;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    protected UserPenalty() {
    }

    public static UserPenalty create(User user, User createdBy, String penaltyType,
                                     String reason, OffsetDateTime endAt) {
        UserPenalty penalty = new UserPenalty();
        penalty.user = user;
        penalty.createdBy = createdBy;
        penalty.penaltyType = penaltyType;
        penalty.reason = reason;
        penalty.startAt = OffsetDateTime.now();
        penalty.endAt = endAt;
        penalty.active = true;
        penalty.createdAt = OffsetDateTime.now();
        return penalty;
    }

    /** 기간이 지났으면 더 이상 유효하지 않습니다. */
    public boolean isCurrentlyEffective(OffsetDateTime at) {
        if (!active) {
            return false;
        }
        return endAt == null || endAt.isAfter(at);
    }

    public void release() {
        this.active = false;
    }

    public Long getId() { return id; }
    public User getUser() { return user; }
    public String getPenaltyType() { return penaltyType; }
    public String getReason() { return reason; }
    public OffsetDateTime getStartAt() { return startAt; }
    public OffsetDateTime getEndAt() { return endAt; }
    public boolean isActive() { return active; }
    public User getCreatedBy() { return createdBy; }
    public OffsetDateTime getCreatedAt() { return createdAt; }
}
