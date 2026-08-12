package com.kyb.lifeinframap.board;

import com.kyb.lifeinframap.account.User;
import com.kyb.lifeinframap.account.UserRepository;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

/** 알림 API 입니다. Django `notification_list` / `notification_read` / `notification_read_all` 을 옮겼습니다. */
@RestController
@RequestMapping("/api/notifications")
public class NotificationController {

    private final NotificationRepository notificationRepository;
    private final UserRepository userRepository;

    public NotificationController(
            NotificationRepository notificationRepository,
            UserRepository userRepository) {
        this.notificationRepository = notificationRepository;
        this.userRepository = userRepository;
    }

    @GetMapping
    @Transactional(readOnly = true)
    public ResponseEntity<?> list(
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(name = "page_size", defaultValue = "20") int pageSize,
            Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        int safePage = Math.max(page, 1);
        int safeSize = Math.min(Math.max(pageSize, 1), 100);

        var result = notificationRepository.findByRecipientIdOrderByCreatedAtDesc(
                user.getId(), PageRequest.of(safePage - 1, safeSize));

        List<Map<String, Object>> items = new ArrayList<>();
        for (Notification notification : result.getContent()) {
            items.add(serialize(notification));
        }

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("count", result.getTotalElements());
        body.put("page", safePage);
        body.put("page_size", safeSize);
        body.put("total_pages", Math.max(result.getTotalPages(), 1));
        body.put("unread_count", notificationRepository.countByRecipientIdAndReadFalse(user.getId()));
        body.put("results", items);
        return ResponseEntity.ok(body);
    }

    @PostMapping("/{notificationId}/read")
    @Transactional
    public ResponseEntity<?> read(@PathVariable Long notificationId, Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        Notification notification = notificationRepository.findById(notificationId).orElse(null);
        if (notification == null || !notification.getRecipient().getId().equals(user.getId())) {
            // 남의 알림인지 없는 알림인지 구분해 알려주지 않습니다.
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("detail", "알림을 찾을 수 없습니다."));
        }
        notification.markRead();
        return ResponseEntity.ok(serialize(notification));
    }

    @PostMapping("/read-all")
    @Transactional
    public ResponseEntity<?> readAll(Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        int updated = notificationRepository.markAllRead(user.getId());
        return ResponseEntity.ok(Map.of("updated", updated, "unread_count", 0));
    }

    private Map<String, Object> serialize(Notification notification) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("id", notification.getId());
        body.put("notification_type", notification.getNotificationType());
        body.put("title", notification.getTitle());
        body.put("message", notification.getMessage());
        body.put("is_read", notification.isRead());
        body.put("sender", notification.getSender() == null ? null : notification.getSender().getId());
        body.put("sender_username",
                notification.getSender() == null ? null : notification.getSender().getUsername());
        body.put("target_post", notification.getTargetPost() == null ? null : notification.getTargetPost().getId());
        body.put("target_comment",
                notification.getTargetComment() == null ? null : notification.getTargetComment().getId());
        body.put("created_at", notification.getCreatedAt());
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
}
