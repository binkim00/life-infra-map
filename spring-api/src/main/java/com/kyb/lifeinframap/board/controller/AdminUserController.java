package com.kyb.lifeinframap.board.controller;

import com.kyb.lifeinframap.board.domain.*;
import com.kyb.lifeinframap.board.repository.*;
import com.kyb.lifeinframap.board.service.*;
import com.kyb.lifeinframap.board.dto.*;

import com.kyb.lifeinframap.account.domain.User;
import com.kyb.lifeinframap.account.repository.UserProfileRepository;
import com.kyb.lifeinframap.account.repository.UserRepository;
import com.kyb.lifeinframap.tier.service.ContributionService;
import jakarta.validation.constraints.NotBlank;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

/** 관리자용 사용자 조회와 제재/알림 발송입니다. */
@RestController
@RequestMapping("/api/admin/users")
public class AdminUserController {

    private final UserRepository userRepository;
    private final UserProfileRepository profileRepository;
    private final UserPenaltyRepository penaltyRepository;
    private final NotificationRepository notificationRepository;
    private final PostRepository postRepository;
    private final CommentRepository commentRepository;
    private final ReportRepository reportRepository;
    private final ContributionService contributionService;
    private final PenaltyService penaltyService;
    private final BoardResponseAssembler assembler;

    public AdminUserController(
            UserRepository userRepository,
            UserProfileRepository profileRepository,
            UserPenaltyRepository penaltyRepository,
            NotificationRepository notificationRepository,
            PostRepository postRepository,
            CommentRepository commentRepository,
            ReportRepository reportRepository,
            ContributionService contributionService,
            PenaltyService penaltyService,
            BoardResponseAssembler assembler) {
        this.userRepository = userRepository;
        this.profileRepository = profileRepository;
        this.penaltyRepository = penaltyRepository;
        this.notificationRepository = notificationRepository;
        this.postRepository = postRepository;
        this.commentRepository = commentRepository;
        this.reportRepository = reportRepository;
        this.contributionService = contributionService;
        this.penaltyService = penaltyService;
        this.assembler = assembler;
    }



    @GetMapping
    @Transactional(readOnly = true)
    public ResponseEntity<?> list(Authentication authentication) {
        ResponseEntity<?> denied = requireStaff(authentication);
        if (denied != null) {
            return denied;
        }
        List<User> users = userRepository.findAll();
        List<Integer> ids = users.stream().map(User::getId).toList();
        Set<Integer> staffIds = users.stream().filter(User::isStaff).map(User::getId).collect(Collectors.toSet());
        Map<Integer, ContributionService.TierInfo> tiers = contributionService.getTierInfo(ids, staffIds);

        List<Map<String, Object>> body = new ArrayList<>();
        for (User user : users) {
            body.add(summarize(user, tiers.get(user.getId())));
        }
        return ResponseEntity.ok(body);
    }

    @GetMapping("/{userId}")
    @Transactional(readOnly = true)
    public ResponseEntity<?> detail(@PathVariable Integer userId, Authentication authentication) {
        ResponseEntity<?> denied = requireStaff(authentication);
        if (denied != null) {
            return denied;
        }
        User user = userRepository.findById(userId).orElse(null);
        if (user == null) {
            return notFound();
        }
        List<Post> authoredPosts = postRepository.findByAuthorIdOrderByCreatedAtDesc(userId);
        List<Comment> authoredComments = commentRepository.findByAuthorIdOrderByCreatedAtDesc(userId);
        BoardResponseAssembler.AuthorContext context = assembler.loadAuthors(List.of(user));

        List<Map<String, Object>> posts = new ArrayList<>();
        authoredPosts.forEach(post -> posts.add(assembler.post(post, context, userId, false)));
        List<Map<String, Object>> comments = new ArrayList<>();
        authoredComments.forEach(comment -> comments.add(assembler.comment(comment, context, userId, List.of())));

        List<Map<String, Object>> penalties = new ArrayList<>();
        for (UserPenalty penalty : penaltyRepository.findByUserIdOrderByCreatedAtDesc(userId)) {
            penalties.add(serializePenalty(penalty));
        }

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("user", summarize(user,
                contributionService.getTierInfo(user.getId(), user.isStaff())));
        body.put("posts", posts);
        body.put("comments", comments);
        body.put("penalties", penalties);
        return ResponseEntity.ok(body);
    }

    @PostMapping("/{userId}/penalties")
    @Transactional
    public ResponseEntity<?> createPenalty(@PathVariable Integer userId,
                                           @RequestBody PenaltyRequest request,
                                           Authentication authentication) {
        ResponseEntity<?> denied = requireStaff(authentication);
        if (denied != null) {
            return denied;
        }
        User target = userRepository.findById(userId).orElse(null);
        if (target == null) {
            return notFound();
        }
        User admin = currentUser(authentication);

        // 기간이 없으면 영구 제재입니다.
        OffsetDateTime endAt = request.days() == null || request.days() <= 0
                ? null : OffsetDateTime.now().plusDays(request.days());
        UserPenalty penalty = penaltyRepository.save(
                UserPenalty.create(target, admin, request.penaltyType(), request.reason(), endAt));

        notificationRepository.save(Notification.create(
                target, admin, "penalty", "제재가 적용되었어요.", request.reason(), null, null));
        return ResponseEntity.status(HttpStatus.CREATED).body(serializePenalty(penalty));
    }

    @PostMapping("/{userId}/notifications")
    @Transactional
    public ResponseEntity<?> createNotification(@PathVariable Integer userId,
                                                @RequestBody NotificationRequest request,
                                                Authentication authentication) {
        ResponseEntity<?> denied = requireStaff(authentication);
        if (denied != null) {
            return denied;
        }
        User target = userRepository.findById(userId).orElse(null);
        if (target == null) {
            return notFound();
        }
        Notification notification = notificationRepository.save(Notification.create(
                target, currentUser(authentication), "admin_message",
                request.title(), request.message(), null, null));
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("id", notification.getId(), "message", "알림을 보냈습니다."));
    }

    private Map<String, Object> summarize(User user, ContributionService.TierInfo tier) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("id", user.getId());
        body.put("username", user.getUsername());
        body.put("nickname", profileRepository.findByUserId(user.getId())
                .map(profile -> profile.getNickname()).orElse(user.getUsername()));
        body.put("email", user.getEmail());
        body.put("is_staff", user.isStaff());
        body.put("is_active", user.isActive());
        body.put("date_joined", user.getDateJoined());
        body.put("last_login", user.getLastLogin());
        body.put("tier", tier == null ? "iron" : tier.tier());
        body.put("tier_label", tier == null ? "아이언" : tier.tierLabel());
        body.put("contribution", tier == null ? 0 : tier.contribution());
        body.put("posts_count", postRepository.countByAuthorId(user.getId()));
        body.put("comments_count", commentRepository.countByAuthorId(user.getId()));
        body.put("received_reports_count",
                reportRepository.countByPostAuthorId(user.getId())
                        + reportRepository.countByCommentAuthorId(user.getId()));
        UserPenalty currentPenalty = penaltyService.findCurrent(user.getId());
        body.put("current_penalty", currentPenalty == null ? null : serializePenalty(currentPenalty));
        List<UserPenalty> penalties = penaltyRepository.findByUserIdOrderByCreatedAtDesc(user.getId());
        body.put("recent_penalty", penalties.isEmpty() ? null : serializePenalty(penalties.get(0)));
        return body;
    }

    private Map<String, Object> serializePenalty(UserPenalty penalty) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("id", penalty.getId());
        body.put("penalty_type", penalty.getPenaltyType());
        body.put("reason", penalty.getReason());
        body.put("start_at", penalty.getStartAt());
        body.put("end_at", penalty.getEndAt());
        body.put("is_active", penalty.isActive());
        body.put("is_current", penalty.isCurrentlyEffective(OffsetDateTime.now()));
        body.put("created_by", penalty.getCreatedBy() == null ? null : penalty.getCreatedBy().getId());
        body.put("created_at", penalty.getCreatedAt());
        return body;
    }

    private ResponseEntity<?> requireStaff(Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(Map.of("detail", "로그인이 필요합니다."));
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

    private ResponseEntity<Map<String, Object>> notFound() {
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("detail", "사용자를 찾을 수 없습니다."));
    }
}
