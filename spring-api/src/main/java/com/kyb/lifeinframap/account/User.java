package com.kyb.lifeinframap.account;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.OffsetDateTime;

/**
 * Django 의 `auth_user` 테이블을 그대로 매핑합니다.
 *
 * 스키마 소유자는 Django 이므로 컬럼을 추가하거나 바꾸지 않습니다.
 * 바꿔야 하면 Django 마이그레이션으로 하고 여기 매핑을 맞춥니다.
 */
@Entity
@Table(name = "auth_user")
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Integer id;

    /** Django 형식의 해시입니다. 예: pbkdf2_sha256$1200000$salt$hash */
    @Column(nullable = false, length = 128)
    private String password;

    @Column(name = "last_login")
    private OffsetDateTime lastLogin;

    @Column(name = "is_superuser", nullable = false)
    private boolean superuser;

    @Column(nullable = false, length = 150, unique = true)
    private String username;

    @Column(name = "first_name", nullable = false, length = 150)
    private String firstName = "";

    @Column(name = "last_name", nullable = false, length = 150)
    private String lastName = "";

    @Column(nullable = false, length = 254)
    private String email = "";

    @Column(name = "is_staff", nullable = false)
    private boolean staff;

    @Column(name = "is_active", nullable = false)
    private boolean active = true;

    @Column(name = "date_joined", nullable = false)
    private OffsetDateTime dateJoined;

    protected User() {
    }

    /**
     * 새 사용자를 만듭니다.
     *
     * Django `create_user` 와 같은 기본값을 씁니다.
     * 비밀번호는 이미 Django 형식으로 해싱된 값을 받습니다.
     */
    public static User create(String username, String email, String encodedPassword) {
        User user = new User();
        user.username = username;
        user.email = email == null ? "" : email;
        user.password = encodedPassword;
        user.firstName = "";
        user.lastName = "";
        user.superuser = false;
        user.staff = false;
        user.active = true;
        user.dateJoined = OffsetDateTime.now();
        return user;
    }

    public void changePassword(String encodedPassword) {
        this.password = encodedPassword;
    }

    public Integer getId() {
        return id;
    }

    public String getPassword() {
        return password;
    }

    public String getUsername() {
        return username;
    }

    public String getEmail() {
        return email;
    }

    public boolean isActive() {
        return active;
    }

    public boolean isStaff() {
        return staff;
    }

    public boolean isSuperuser() {
        return superuser;
    }

    public OffsetDateTime getLastLogin() {
        return lastLogin;
    }

    public void markLoggedIn(OffsetDateTime at) {
        this.lastLogin = at;
    }
}
