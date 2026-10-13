package com.kyb.lifeinframap.auth.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.OffsetDateTime;

@Entity
@Table(name = "accounts_socialloginticket")
public class SocialLoginTicket {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(name = "user_id", nullable = false)
    private Integer userId;
    @Column(name = "ticket_hash", nullable = false, length = 64, unique = true)
    private String ticketHash;
    @Column(name = "expires_at", nullable = false)
    private OffsetDateTime expiresAt;
    @Column(name = "consumed_at")
    private OffsetDateTime consumedAt;
    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    protected SocialLoginTicket() {}
    public SocialLoginTicket(Integer userId, String ticketHash) {
        this.userId = userId;
        this.ticketHash = ticketHash;
        this.createdAt = OffsetDateTime.now();
        this.expiresAt = createdAt.plusMinutes(2);
    }
    public boolean isActive(OffsetDateTime now) { return consumedAt == null && expiresAt.isAfter(now); }
    public void consume(OffsetDateTime now) { consumedAt = now; }
    public Integer getUserId() { return userId; }
}
