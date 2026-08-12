package com.kyb.lifeinframap.board;

import com.kyb.lifeinframap.account.User;
import com.kyb.lifeinframap.account.UserRepository;
import jakarta.validation.constraints.NotBlank;
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

/** 문의 API 입니다. 사용자는 자기 문의만 보고, 관리자는 전체를 보고 답변합니다. */
@RestController
@RequestMapping("/api")
public class InquiryController {

    private final InquiryRepository inquiryRepository;
    private final NotificationRepository notificationRepository;
    private final UserRepository userRepository;

    public InquiryController(
            InquiryRepository inquiryRepository,
            NotificationRepository notificationRepository,
            UserRepository userRepository) {
        this.inquiryRepository = inquiryRepository;
        this.notificationRepository = notificationRepository;
        this.userRepository = userRepository;
    }

    public record InquiryRequest(@NotBlank String title, @NotBlank String content) {
    }

    public record InquiryReplyRequest(String status, String adminReply) {
    }

    @PostMapping("/inquiries")
    @Transactional
    public ResponseEntity<?> create(@RequestBody InquiryRequest request, Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        Inquiry inquiry = inquiryRepository.save(Inquiry.create(user, request.title(), request.content()));
        return ResponseEntity.status(HttpStatus.CREATED).body(serialize(inquiry));
    }

    @GetMapping("/inquiries/my")
    @Transactional(readOnly = true)
    public ResponseEntity<?> myList(
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(name = "page_size", defaultValue = "20") int pageSize,
            Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        var result = inquiryRepository.findByAuthorIdOrderByCreatedAtDesc(
                user.getId(), PageRequest.of(Math.max(page, 1) - 1, clamp(pageSize)));
        return ResponseEntity.ok(paged(result.getContent(), result.getTotalElements(),
                Math.max(page, 1), clamp(pageSize), result.getTotalPages()));
    }

    @GetMapping("/inquiries/{inquiryId}")
    @Transactional(readOnly = true)
    public ResponseEntity<?> detail(@PathVariable Long inquiryId, Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        Inquiry inquiry = inquiryRepository.findById(inquiryId).orElse(null);
        if (inquiry == null) {
            return notFound();
        }
        // 본인 문의이거나 관리자여야 볼 수 있습니다.
        if (!inquiry.getAuthor().getId().equals(user.getId()) && !user.isStaff()) {
            return notFound();
        }
        return ResponseEntity.ok(serialize(inquiry));
    }

    @GetMapping("/admin/inquiries")
    @Transactional(readOnly = true)
    public ResponseEntity<?> adminList(
            @RequestParam(required = false) String status,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(name = "page_size", defaultValue = "20") int pageSize,
            Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        if (!user.isStaff()) {
            return forbidden();
        }
        var pageable = PageRequest.of(Math.max(page, 1) - 1, clamp(pageSize),
                Sort.by(Sort.Order.desc("createdAt")));
        var result = status == null || status.isBlank()
                ? inquiryRepository.findAll(pageable)
                : inquiryRepository.findByStatus(status, pageable);
        return ResponseEntity.ok(paged(result.getContent(), result.getTotalElements(),
                Math.max(page, 1), clamp(pageSize), result.getTotalPages()));
    }

    @PatchMapping("/admin/inquiries/{inquiryId}")
    @Transactional
    public ResponseEntity<?> adminReply(@PathVariable Long inquiryId,
                                        @RequestBody InquiryReplyRequest request,
                                        Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        if (!user.isStaff()) {
            return forbidden();
        }
        Inquiry inquiry = inquiryRepository.findById(inquiryId).orElse(null);
        if (inquiry == null) {
            return notFound();
        }
        String status = request.status() == null || request.status().isBlank()
                ? "answered" : request.status();
        inquiry.reply(user, status, request.adminReply());

        if (request.adminReply() != null && !request.adminReply().isBlank()) {
            notificationRepository.save(Notification.create(
                    inquiry.getAuthor(), user, "inquiry_answered",
                    "문의에 답변이 등록되었어요.", request.adminReply(), null, null));
        }
        return ResponseEntity.ok(serialize(inquiry));
    }

    private Map<String, Object> paged(List<Inquiry> items, long total, int page, int pageSize, int totalPages) {
        List<Map<String, Object>> results = new ArrayList<>();
        for (Inquiry inquiry : items) {
            results.add(serialize(inquiry));
        }
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("count", total);
        body.put("page", page);
        body.put("page_size", pageSize);
        body.put("total_pages", Math.max(totalPages, 1));
        body.put("results", results);
        return body;
    }

    private Map<String, Object> serialize(Inquiry inquiry) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("id", inquiry.getId());
        body.put("author", inquiry.getAuthor().getId());
        body.put("author_username", inquiry.getAuthor().getUsername());
        body.put("title", inquiry.getTitle());
        body.put("content", inquiry.getContent());
        body.put("status", inquiry.getStatus());
        body.put("admin_reply", inquiry.getAdminReply());
        body.put("replied_by", inquiry.getRepliedBy() == null ? null : inquiry.getRepliedBy().getId());
        body.put("replied_at", inquiry.getRepliedAt());
        body.put("created_at", inquiry.getCreatedAt());
        body.put("updated_at", inquiry.getUpdatedAt());
        return body;
    }

    private int clamp(int pageSize) {
        return Math.min(Math.max(pageSize, 1), 100);
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

    private ResponseEntity<Map<String, Object>> forbidden() {
        return ResponseEntity.status(HttpStatus.FORBIDDEN).body(Map.of("detail", "권한이 없습니다."));
    }

    private ResponseEntity<Map<String, Object>> notFound() {
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("detail", "문의를 찾을 수 없습니다."));
    }
}
