package com.kyb.lifeinframap.place;

import com.kyb.lifeinframap.account.User;
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.List;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/**
 * Django `recommendations_placereport` 매핑. 장소 오류 제보와 신규 장소 제안입니다.
 *
 * 승인된 제보는 사용자 기여도 점수가 되므로 등급 계산과 함께 Spring 이 가집니다.
 * 승인해도 `Place` 를 직접 고치지 않습니다. 장소 데이터는 Django 가 소유합니다.
 */
@Entity
@Table(name = "recommendations_placereport")
public class PlaceReport {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    /** 신규 장소 제안이면 비어 있습니다. */
    @Column(name = "place_id")
    private Long placeId;

    @Column(name = "report_type", nullable = false, length = 30)
    private String reportType;

    @Column(nullable = false, length = 20)
    private String status;

    @Column(name = "suggested_name", nullable = false, length = 255)
    private String suggestedName = "";

    @Column(name = "suggested_category", nullable = false, length = 50)
    private String suggestedCategory = "";

    @Column(name = "suggested_address", nullable = false, length = 255)
    private String suggestedAddress = "";

    @Column(name = "suggested_lat", precision = 9, scale = 6)
    private BigDecimal suggestedLat;

    @Column(name = "suggested_lng", precision = 9, scale = 6)
    private BigDecimal suggestedLng;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "suggested_tags", nullable = false, columnDefinition = "jsonb")
    private List<String> suggestedTags = List.of();

    @Column(nullable = false, columnDefinition = "text")
    private String description = "";

    @Column(name = "admin_note", nullable = false, columnDefinition = "text")
    private String adminNote = "";

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "reviewed_by_id")
    private User reviewedBy;

    @Column(name = "reviewed_at")
    private OffsetDateTime reviewedAt;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    protected PlaceReport() {
    }

    public static PlaceReport create(User user, Long placeId, String reportType, String description) {
        PlaceReport report = new PlaceReport();
        report.user = user;
        report.placeId = placeId;
        report.reportType = reportType;
        report.description = description == null ? "" : description;
        report.status = "pending";
        OffsetDateTime now = OffsetDateTime.now();
        report.createdAt = now;
        report.updatedAt = now;
        return report;
    }

    public void suggest(String name, String category, String address,
                        BigDecimal lat, BigDecimal lng, List<String> tags) {
        if (name != null) this.suggestedName = name;
        if (category != null) this.suggestedCategory = category;
        if (address != null) this.suggestedAddress = address;
        this.suggestedLat = lat;
        this.suggestedLng = lng;
        if (tags != null) this.suggestedTags = tags;
        this.updatedAt = OffsetDateTime.now();
    }

    public void review(User admin, String status, String adminNote) {
        this.status = status;
        this.adminNote = adminNote == null ? "" : adminNote;
        this.reviewedBy = admin;
        this.reviewedAt = OffsetDateTime.now();
        this.updatedAt = OffsetDateTime.now();
    }

    public Long getId() { return id; }
    public User getUser() { return user; }
    public Long getPlaceId() { return placeId; }
    public String getReportType() { return reportType; }
    public String getStatus() { return status; }
    public String getSuggestedName() { return suggestedName; }
    public String getSuggestedCategory() { return suggestedCategory; }
    public String getSuggestedAddress() { return suggestedAddress; }
    public BigDecimal getSuggestedLat() { return suggestedLat; }
    public BigDecimal getSuggestedLng() { return suggestedLng; }
    public List<String> getSuggestedTags() { return suggestedTags; }
    public String getDescription() { return description; }
    public String getAdminNote() { return adminNote; }
    public User getReviewedBy() { return reviewedBy; }
    public OffsetDateTime getReviewedAt() { return reviewedAt; }
    public OffsetDateTime getCreatedAt() { return createdAt; }
    public OffsetDateTime getUpdatedAt() { return updatedAt; }
}
