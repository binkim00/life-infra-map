package com.kyb.lifeinframap.auth.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.OffsetDateTime;

@Entity
@Table(name = "accounts_refreshsession")
public class RefreshSession {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(name = "user_id", nullable = false)
    private Integer userId;
    @Column(name = "token_hash", nullable = false, length = 64, unique = true)
    private String tokenHash;
    @Column(name = "expires_at", nullable = false)
    private OffsetDateTime expiresAt;
    @Column(name = "revoked_at")
    private OffsetDateTime revokedAt;
    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    protected RefreshSession() {}

    public static RefreshSession create(Integer userId, String tokenHash, OffsetDateTime expiresAt) {
        RefreshSession session = new RefreshSession();
        session.userId = userId;
        session.tokenHash = tokenHash;
        session.expiresAt = expiresAt;
        session.createdAt = OffsetDateTime.now();
        return session;
    }

    public boolean isActive(OffsetDateTime now) { return revokedAt == null && expiresAt.isAfter(now); }
    public void revoke(OffsetDateTime now) { revokedAt = now; }
    public Integer getUserId() { return userId; }
}
