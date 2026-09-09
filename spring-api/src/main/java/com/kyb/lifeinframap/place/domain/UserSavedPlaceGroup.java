package com.kyb.lifeinframap.place.domain;

import com.kyb.lifeinframap.account.domain.User;
import jakarta.persistence.*;
import java.time.OffsetDateTime;

/** Django `recommendations_usersavedplacegroup` 테이블의 Spring 매핑입니다. */
@Entity
@Table(name = "recommendations_usersavedplacegroup")
public class UserSavedPlaceGroup {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @Column(nullable = false, length = 100)
    private String name;

    @Column(nullable = false, columnDefinition = "text")
    private String memo = "";

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    protected UserSavedPlaceGroup() {
    }

    public static UserSavedPlaceGroup create(User user, String name, String memo) {
        UserSavedPlaceGroup group = new UserSavedPlaceGroup();
        group.user = user;
        group.name = name;
        group.memo = memo == null ? "" : memo;
        OffsetDateTime now = OffsetDateTime.now();
        group.createdAt = now;
        group.updatedAt = now;
        return group;
    }

    public void update(String name, String memo) {
        if (name != null) this.name = name;
        if (memo != null) this.memo = memo;
        this.updatedAt = OffsetDateTime.now();
    }

    public Long getId() { return id; }
    public User getUser() { return user; }
    public String getName() { return name; }
    public String getMemo() { return memo; }
    public OffsetDateTime getCreatedAt() { return createdAt; }
    public OffsetDateTime getUpdatedAt() { return updatedAt; }
}
