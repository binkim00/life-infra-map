package com.kyb.lifeinframap.place;

import com.kyb.lifeinframap.account.User;
import com.kyb.lifeinframap.account.UserRepository;
import com.kyb.lifeinframap.board.Notification;
import com.kyb.lifeinframap.board.NotificationRepository;
import jakarta.validation.constraints.NotBlank;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

/**
 * 장소 오류 제보와 신규 장소 제안입니다.
 *
 * 승인된 제보는 사용자 기여도가 되므로 등급 계산과 같은 쪽에 둡니다.
 * 승인해도 `Place` 를 직접 고치지 않습니다. 장소 데이터 반영은 Django 쪽 작업입니다.
 */
@RestController
@RequestMapping("/api/recommendations")
public class PlaceReportController {

    private final PlaceReportRepository reportRepository;
    private final NotificationRepository notificationRepository;
    private final UserRepository userRepository;

    public PlaceReportController(
            PlaceReportRepository reportRepository,
            NotificationRepository notificationRepository,
            UserRepository userRepository) {
        this.reportRepository = reportRepository;
        this.notificationRepository = notificationRepository;
        this.userRepository = userRepository;
    }

    public record ReportRequest(@NotBlank String reportType, Long place, String description,
                                String suggestedName, String suggestedCategory, String suggestedAddress,
                                BigDecimal suggestedLat, BigDecimal suggestedLng, List<String> suggestedTags) {
    }

    public record ReviewRequest(String adminNote) {
    }

    @PostMapping("/place-reports")
    @Transactional
    public ResponseEntity<?> create(@RequestBody ReportRequest request, Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        PlaceReport report = PlaceReport.create(user, request.place(), request.reportType(), request.description());
        report.suggest(request.suggestedName(), request.suggestedCategory(), request.suggestedAddress(),
                request.suggestedLat(), request.suggestedLng(), request.suggestedTags());
        reportRepository.save(report);
        return ResponseEntity.status(HttpStatus.CREATED).body(serialize(report));
    }

    @GetMapping("/place-reports")
    @Transactional(readOnly = true)
    public ResponseEntity<?> myList(
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(name = "page_size", defaultValue = "10") int pageSize,
            Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        int safePage = Math.max(page, 1);
        int safeSize = Math.min(Math.max(pageSize, 1), 100);
        var result = reportRepository.findByUserIdOrderByCreatedAtDesc(
                user.getId(), PageRequest.of(safePage - 1, safeSize));
        return ResponseEntity.ok(paged(result.getContent(), result.getTotalElements(),
                safePage, safeSize, result.getTotalPages()));
    }

    @GetMapping("/admin/place-reports")
    @Transactional(readOnly = true)
    public ResponseEntity<?> adminList(
            @RequestParam(required = false) String status,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(name = "page_size", defaultValue = "10") int pageSize,
            Authentication authentication) {
        ResponseEntity<?> denied = requireStaff(authentication);
        if (denied != null) {
            return denied;
        }
        int safePage = Math.max(page, 1);
        int safeSize = Math.min(Math.max(pageSize, 1), 100);
        var pageable = PageRequest.of(safePage - 1, safeSize, Sort.by(Sort.Order.desc("createdAt")));
        var result = status == null || status.isBlank()
                ? reportRepository.findAll(pageable)
                : reportRepository.findByStatus(status, pageable);
        return ResponseEntity.ok(paged(result.getContent(), result.getTotalElements(),
                safePage, safeSize, result.getTotalPages()));
    }

    @PostMapping("/admin/place-reports/{reportId}/approve")
    @Transactional
    public ResponseEntity<?> approve(@PathVariable Long reportId, @RequestBody(required = false) ReviewRequest request,
                                     Authentication authentication) {
        return review(reportId, request, authentication, "approved", "제보가 반영되었어요.");
    }

    @PostMapping("/admin/place-reports/{reportId}/reject")
    @Transactional
    public ResponseEntity<?> reject(@PathVariable Long reportId, @RequestBody(required = false) ReviewRequest request,
                                    Authentication authentication) {
        return review(reportId, request, authentication, "rejected", "제보가 반려되었어요.");
    }

    private ResponseEntity<?> review(Long reportId, ReviewRequest request, Authentication authentication,
                                     String status, String notificationTitle) {
        ResponseEntity<?> denied = requireStaff(authentication);
        if (denied != null) {
            return denied;
        }
        PlaceReport report = reportRepository.findById(reportId).orElse(null);
        if (report == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("detail", "제보를 찾을 수 없습니다."));
        }
        String adminNote = request == null ? "" : request.adminNote();
        report.review(currentUser(authentication), status, adminNote);

        // 승인되면 기여도가 올라가므로 사용자에게 알립니다.
        notificationRepository.save(Notification.create(
                report.getUser(), currentUser(authentication), "place_report_" + status,
                notificationTitle, adminNote == null ? "" : adminNote, null, null));
        return ResponseEntity.ok(serialize(report));
    }

    private Map<String, Object> paged(List<PlaceReport> items, long total, int page, int pageSize, int totalPages) {
        List<Map<String, Object>> results = new ArrayList<>();
        for (PlaceReport report : items) {
            results.add(serialize(report));
        }
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("count", total);
        body.put("page", page);
        body.put("page_size", pageSize);
        body.put("total_pages", Math.max(totalPages, 1));
        body.put("results", results);
        return body;
    }

    private Map<String, Object> serialize(PlaceReport report) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("id", report.getId());
        body.put("user", report.getUser().getId());
        body.put("user_username", report.getUser().getUsername());
        body.put("place", report.getPlaceId());
        body.put("report_type", report.getReportType());
        body.put("status", report.getStatus());
        body.put("suggested_name", report.getSuggestedName());
        body.put("suggested_category", report.getSuggestedCategory());
        body.put("suggested_address", report.getSuggestedAddress());
        body.put("suggested_lat", report.getSuggestedLat());
        body.put("suggested_lng", report.getSuggestedLng());
        body.put("suggested_tags", report.getSuggestedTags());
        body.put("description", report.getDescription());
        body.put("admin_note", report.getAdminNote());
        body.put("reviewed_by", report.getReviewedBy() == null ? null : report.getReviewedBy().getId());
        body.put("reviewed_at", report.getReviewedAt());
        body.put("created_at", report.getCreatedAt());
        body.put("updated_at", report.getUpdatedAt());
        return body;
    }

    private ResponseEntity<?> requireStaff(Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        if (!user.isStaff()) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN).body(Map.of("detail", "권한이 없습니다."));
        }
        return null;
    }

    private User currentUser(Authentication authentication) {
        if (authentication == null || authentication.getName() == null) {
            return null;
        }
        try {
            return userRepository.findById(Integer.valueOf(authentication.getName())).orElse(null);
        } catch (NumberFormatException exception) {
            return null;
        }
    }

    private ResponseEntity<Map<String, Object>> unauthorized() {
        return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(Map.of("detail", "로그인이 필요합니다."));
    }
}
