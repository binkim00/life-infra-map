package com.kyb.lifeinframap.auth.domain;

import com.kyb.lifeinframap.account.domain.User;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.OffsetDateTime;

@Entity
@Table(name = "accounts_socialidentity", uniqueConstraints =
        @UniqueConstraint(name = "social_identity_provider_subject_unique", columnNames = {"provider", "provider_subject"}))
public class SocialIdentity {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @ManyToOne @JoinColumn(name = "user_id", nullable = false)
    private User user;
    @Column(nullable = false, length = 16)
    private String provider;
    @Column(name = "provider_subject", nullable = false, length = 255)
    private String providerSubject;
    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    protected SocialIdentity() {}

    public SocialIdentity(User user, String provider, String providerSubject) {
        this.user = user;
        this.provider = provider;
        this.providerSubject = providerSubject;
        this.createdAt = OffsetDateTime.now();
    }

    public User getUser() { return user; }
}
