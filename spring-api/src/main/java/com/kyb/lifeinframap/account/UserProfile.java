package com.kyb.lifeinframap.account;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;
import java.time.OffsetDateTime;

/**
 * Django 의 `accounts_userprofile` 테이블을 매핑합니다.
 *
 * `profile_image` 는 저장소 키만 담습니다. 실제 파일은 S3 호환 저장소에 있습니다.
 */
@Entity
@Table(name = "accounts_userprofile")
public class UserProfile {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne
    @JoinColumn(name = "user_id", nullable = false, unique = true)
    private User user;

    @Column(nullable = false, length = 50, unique = true)
    private String nickname;

    @Column(name = "profile_image", length = 100)
    private String profileImage;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    protected UserProfile() {
    }

    public UserProfile(User user, String nickname) {
        this.user = user;
        this.nickname = nickname;
        OffsetDateTime now = OffsetDateTime.now();
        this.createdAt = now;
        this.updatedAt = now;
    }

    public Long getId() {
        return id;
    }

    public User getUser() {
        return user;
    }

    public String getNickname() {
        return nickname;
    }

    public String getProfileImage() {
        return profileImage;
    }

    /** 저장소에 올라간 파일 키만 바꿉니다. 파일 자체는 S3 호환 저장소에 있습니다. */
    public void changeProfileImage(String profileImage) {
        this.profileImage = profileImage;
        this.updatedAt = OffsetDateTime.now();
    }

    public void changeNickname(String nickname) {
        this.nickname = nickname;
        this.updatedAt = OffsetDateTime.now();
    }
}
