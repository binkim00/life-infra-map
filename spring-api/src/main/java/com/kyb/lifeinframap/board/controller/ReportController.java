package com.kyb.lifeinframap.board.controller;

import com.kyb.lifeinframap.board.domain.*;
import com.kyb.lifeinframap.board.repository.*;
import com.kyb.lifeinframap.board.service.*;
import com.kyb.lifeinframap.board.dto.*;

import com.kyb.lifeinframap.account.domain.User;
import com.kyb.lifeinframap.account.repository.UserRepository;
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

/**
 * 게시글/댓글 신고와 관리자 처리입니다.
 *
 * 같은 대상을 두 번 신고할 수 없습니다. 처리하면 신고자에게 알림을 보냅니다.
 */
@RestController
@RequestMapping("/api/boards")
public class ReportController {

    private final ReportRepository reportRepository;
    private final PostRepository postRepository;
    private final CommentRepository commentRepository;
    private final NotificationRepository notificationRepository;
    private final UserRepository userRepository;
    private final PenaltyService penaltyService;

    public ReportController(
            ReportRepository reportRepository,
            PostRepository postRepository,
            CommentRepository commentRepository,
            NotificationRepository notificationRepository,
            UserRepository userRepository,
            PenaltyService penaltyService) {
        this.reportRepository = reportRepository;
        this.postRepository = postRepository;
        this.commentRepository = commentRepository;
        this.notificationRepository = notificationRepository;
        this.userRepository = userRepository;
        this.penaltyService = penaltyService;
    }



    @PostMapping("/posts/{postId}/report")
    @Transactional
    public ResponseEntity<?> reportPost(@PathVariable Long postId, @RequestBody ReportRequest request,
                                        Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        UserPenalty penalty = penaltyService.findCurrent(user.getId());
        if (penalty != null) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN).body(penaltyService.blockedBody(penalty));
        }
        Post post = postRepository.findById(postId).orElse(null);
        if (post == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("detail", "게시글을 찾을 수 없습니다."));
        }
        if (post.getAuthor().getId().equals(user.getId())) {
            return ResponseEntity.badRequest().body(Map.of("detail", "본인 글은 신고할 수 없습니다."));
        }
        if (reportRepository.existsByReporterIdAndPostId(user.getId(), postId)) {
            return ResponseEntity.badRequest().body(Map.of("detail", "이미 신고한 게시글입니다."));
        }

        Report report = reportRepository.save(Report.create(user, post, null, request.reason()));
        notifyStaff(user, "게시글 신고가 접수되었어요.", request.reason(), post, null);
        return ResponseEntity.status(HttpStatus.CREATED).body(serialize(report));
    }

    @PostMapping("/comments/{commentId}/report")
    @Transactional
    public ResponseEntity<?> reportComment(@PathVariable Long commentId, @RequestBody ReportRequest request,
                                           Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        UserPenalty penalty = penaltyService.findCurrent(user.getId());
        if (penalty != null) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN).body(penaltyService.blockedBody(penalty));
        }
        Comment comment = commentRepository.findById(commentId).orElse(null);
        if (comment == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("detail", "댓글을 찾을 수 없습니다."));
        }
        if (comment.getAuthor().getId().equals(user.getId())) {
            return ResponseEntity.badRequest().body(Map.of("detail", "본인 댓글은 신고할 수 없습니다."));
        }
        if (reportRepository.existsByReporterIdAndCommentId(user.getId(), commentId)) {
            return ResponseEntity.badRequest().body(Map.of("detail", "이미 신고한 댓글입니다."));
        }

        Report report = reportRepository.save(Report.create(user, null, comment, request.reason()));
        notifyStaff(user, "댓글 신고가 접수되었어요.", request.reason(), null, comment);
        return ResponseEntity.status(HttpStatus.CREATED).body(serialize(report));
    }

    @GetMapping("/reports")
    @Transactional(readOnly = true)
    public ResponseEntity<?> list(
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
        int safePage = Math.max(page, 1);
        int safeSize = Math.min(Math.max(pageSize, 1), 100);
        var pageable = PageRequest.of(safePage - 1, safeSize, Sort.by(Sort.Order.desc("createdAt")));
        var result = status == null || status.isBlank()
                ? reportRepository.findAll(pageable)
                : reportRepository.findByStatus(status, pageable);

        // 배열을 그대로 내려줍니다. Django `report_list` 가 `Response(serializer.data)` 이고,
        // 프론트 `ReportListView` 의 `initializeReportState` 가 `reportList.map()` 을 씁니다.
        // 페이지네이션 객체로 감싸면 신고 관리 화면이 깨집니다.
        List<Map<String, Object>> items = new ArrayList<>();
        for (Report report : result.getContent()) {
            items.add(serialize(report));
        }
        return ResponseEntity.ok(items);
    }

    @PostMapping("/reports/{reportId}/process")
    @Transactional
    public ResponseEntity<?> process(@PathVariable Long reportId, @RequestBody ProcessRequest request,
                                     Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        if (!user.isStaff()) {
            return forbidden();
        }
        Report report = reportRepository.findById(reportId).orElse(null);
        if (report == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("detail", "신고를 찾을 수 없습니다."));
        }
        String status = request.status() == null || request.status().isBlank()
                ? "resolved" : request.status();
        report.process(user, status, request.adminMemo());

        notificationRepository.save(Notification.create(
                report.getReporter(), user, "report_processed",
                "신고가 처리되었어요.", request.adminMemo() == null ? "" : request.adminMemo(),
                report.getPost(), report.getComment()));
        return ResponseEntity.ok(serialize(report));
    }

    /** 관리자 전원에게 신고 접수 알림을 보냅니다. */
    private void notifyStaff(User reporter, String title, String message, Post post, Comment comment) {
        for (User staff : userRepository.findAll()) {
            if (!staff.isStaff() || staff.getId().equals(reporter.getId())) {
                continue;
            }
            notificationRepository.save(Notification.create(
                    staff, reporter, "report_received", title, message, post, comment));
        }
    }

    private Map<String, Object> serialize(Report report) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("id", report.getId());
        body.put("reporter", report.getReporter().getId());
        body.put("reporter_username", report.getReporter().getUsername());
        body.put("post", report.getPost() == null ? null : report.getPost().getId());
        body.put("post_title", report.getPost() == null ? null : report.getPost().getTitle());
        body.put("comment", report.getComment() == null ? null : report.getComment().getId());
        body.put("comment_content", report.getComment() == null ? null : report.getComment().getContent());
        body.put("reason", report.getReason());
        body.put("status", report.getStatus());
        body.put("admin_memo", report.getAdminMemo());
        body.put("processed_by", report.getProcessedBy() == null ? null : report.getProcessedBy().getId());
        body.put("processed_at", report.getProcessedAt());
        body.put("created_at", report.getCreatedAt());
        return body;
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
}
