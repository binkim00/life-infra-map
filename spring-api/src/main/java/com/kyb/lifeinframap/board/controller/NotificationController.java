package com.kyb.lifeinframap.board.controller;

import com.kyb.lifeinframap.board.domain.*;
import com.kyb.lifeinframap.board.repository.*;
import com.kyb.lifeinframap.board.service.*;
import com.kyb.lifeinframap.board.dto.*;

import com.kyb.lifeinframap.account.domain.User;
import com.kyb.lifeinframap.account.repository.UserRepository;
import java.util.ArrayList;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
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
    @Transactional
    public ResponseEntity<?> list(Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        // Django 는 목록을 볼 때 3일 지난 알림을 정리합니다. 같은 규칙을 씁니다.
        notificationRepository.deleteOlderThan(user.getId(), OffsetDateTime.now().minusDays(3));

        List<Map<String, Object>> items = new ArrayList<>();
        for (Notification notification : notificationRepository.findByRecipientIdOrderByCreatedAtDesc(user.getId())) {
            items.add(serialize(notification));
        }
        // 페이지 정보 없이 배열만 돌려줍니다. 프론트가 그대로 배열로 다룹니다.
        return ResponseEntity.ok(items);
    }

    @PatchMapping("/{notificationId}/read")
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

    @PatchMapping("/read-all")
    @Transactional
    public ResponseEntity<?> readAll(Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        notificationRepository.markAllRead(user.getId());
        return ResponseEntity.ok(Map.of("message", "모든 알림을 읽음 처리했습니다."));
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
