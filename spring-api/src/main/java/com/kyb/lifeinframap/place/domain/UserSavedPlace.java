package com.kyb.lifeinframap.place.domain;

import com.kyb.lifeinframap.place.domain.*;
import com.kyb.lifeinframap.place.repository.*;
import com.kyb.lifeinframap.place.dto.*;

import com.kyb.lifeinframap.account.domain.User;
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.Map;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/**
 * Django `recommendations_usersavedplace` 매핑.
 *
 * 저장 시점의 장소 정보를 그대로 복사해 둡니다. 카카오 장소처럼 DB 에 없는 곳도 저장할 수 있어야 하므로
 * `place_id` 는 비어 있을 수 있습니다.
 */
@Entity
@Table(name = "recommendations_usersavedplace")
public class UserSavedPlace {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    /** 검색은 Django 가 담당하므로 장소는 id 로만 참조합니다. */
    @Column(name = "place_id")
    private Long placeId;

    @Column(name = "place_key", nullable = false, length = 255)
    private String placeKey;

    @Column(nullable = false, length = 30)
    private String source;

    @Column(name = "external_id", nullable = false, length = 100)
    private String externalId = "";

    @Column(nullable = false, length = 200)
    private String name;

    @Column(nullable = false, length = 100)
    private String category = "";

    @Column(nullable = false, length = 255)
    private String address = "";

    @Column(precision = 9, scale = 6)
    private BigDecimal lat;

    @Column(precision = 9, scale = 6)
    private BigDecimal lng;

    @Column(name = "detail_url", nullable = false, length = 500)
    private String detailUrl = "";

    @Column(name = "kakao_place_url", nullable = false, length = 500)
    private String kakaoPlaceUrl = "";

    @Column(nullable = false, length = 50)
    private String phone = "";

    @Column(nullable = false, columnDefinition = "text")
    private String memo = "";

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(nullable = false, columnDefinition = "jsonb")
    private Map<String, Object> raw = Map.of();

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    protected UserSavedPlace() {
    }

    public static UserSavedPlace create(User user, String placeKey, String source, String name) {
        UserSavedPlace saved = new UserSavedPlace();
        saved.user = user;
        saved.placeKey = placeKey;
        saved.source = source;
        saved.name = name;
        OffsetDateTime now = OffsetDateTime.now();
        saved.createdAt = now;
        saved.updatedAt = now;
        return saved;
    }

    public void touch() {
        this.updatedAt = OffsetDateTime.now();
    }

    public void changeMemo(String memo) {
        this.memo = memo == null ? "" : memo;
        touch();
    }

    public void fill(Long placeId, String externalId, String category, String address,
                     BigDecimal lat, BigDecimal lng, String detailUrl, String kakaoPlaceUrl,
                     String phone, String memo, Map<String, Object> raw) {
        this.placeId = placeId;
        if (externalId != null) this.externalId = externalId;
        if (category != null) this.category = category;
        if (address != null) this.address = address;
        this.lat = lat;
        this.lng = lng;
        if (detailUrl != null) this.detailUrl = detailUrl;
        if (kakaoPlaceUrl != null) this.kakaoPlaceUrl = kakaoPlaceUrl;
        if (phone != null) this.phone = phone;
        if (memo != null) this.memo = memo;
        if (raw != null) this.raw = raw;
        touch();
    }

    public Long getId() { return id; }
    public User getUser() { return user; }
    public Long getPlaceId() { return placeId; }
    public String getPlaceKey() { return placeKey; }
    public String getSource() { return source; }
    public String getExternalId() { return externalId; }
    public String getName() { return name; }
    public String getCategory() { return category; }
    public String getAddress() { return address; }
    public BigDecimal getLat() { return lat; }
    public BigDecimal getLng() { return lng; }
    public String getDetailUrl() { return detailUrl; }
    public String getKakaoPlaceUrl() { return kakaoPlaceUrl; }
    public String getPhone() { return phone; }
    public String getMemo() { return memo; }
    public Map<String, Object> getRaw() { return raw; }
    public OffsetDateTime getCreatedAt() { return createdAt; }
    public OffsetDateTime getUpdatedAt() { return updatedAt; }
}
