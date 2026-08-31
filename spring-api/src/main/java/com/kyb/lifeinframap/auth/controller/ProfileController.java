package com.kyb.lifeinframap.auth.controller;

import com.kyb.lifeinframap.auth.dto.*;

import com.kyb.lifeinframap.account.domain.User;
import com.kyb.lifeinframap.account.domain.UserProfile;
import com.kyb.lifeinframap.account.repository.UserProfileRepository;
import com.kyb.lifeinframap.account.repository.UserRepository;
import com.kyb.lifeinframap.board.domain.*;
import com.kyb.lifeinframap.board.repository.*;
import com.kyb.lifeinframap.board.service.*;
import com.kyb.lifeinframap.tier.service.ContributionService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
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

/**
 * 프로필과 마이페이지를 담당하는 Spring 엔드포인트입니다.
 *
 * 로그아웃은 토큰을 서버에 저장하지 않는 방식이라 서버가 할 일이 없습니다.
 * 프론트가 토큰을 지우면 끝나므로 응답만 맞춰 줍니다.
 */
@RestController
@RequestMapping("/api/accounts")
public class ProfileController {

    private final UserRepository userRepository;
    private final UserProfileRepository profileRepository;
    private final ContributionService contributionService;
    private final PostRepository postRepository;
    private final PostLikeRepository postLikeRepository;
    private final CommentRepository commentRepository;
    private final NotificationRepository notificationRepository;
    private final InquiryRepository inquiryRepository;
    private final PenaltyService penaltyService;
    private final BoardResponseAssembler assembler;
    private final com.kyb.lifeinframap.storage.service.StorageService storageService;
    private final com.kyb.lifeinframap.account.service.UserPayloadFactory userPayloadFactory;

    public ProfileController(
            UserRepository userRepository,
            UserProfileRepository profileRepository,
            ContributionService contributionService,
            PostRepository postRepository,
            PostLikeRepository postLikeRepository,
            CommentRepository commentRepository,
            NotificationRepository notificationRepository,
            InquiryRepository inquiryRepository,
            PenaltyService penaltyService,
            BoardResponseAssembler assembler,
            com.kyb.lifeinframap.storage.service.StorageService storageService,
            com.kyb.lifeinframap.account.service.UserPayloadFactory userPayloadFactory) {
        this.userRepository = userRepository;
        this.profileRepository = profileRepository;
        this.contributionService = contributionService;
        this.postRepository = postRepository;
        this.postLikeRepository = postLikeRepository;
        this.commentRepository = commentRepository;
        this.notificationRepository = notificationRepository;
        this.inquiryRepository = inquiryRepository;
        this.penaltyService = penaltyService;
        this.assembler = assembler;
        this.storageService = storageService;
        this.userPayloadFactory = userPayloadFactory;
    }



    @PostMapping("/logout")
    public ResponseEntity<?> logout(Authentication authentication) {
        if (currentUser(authentication) == null) {
            return unauthorized();
        }
        return ResponseEntity.ok(Map.of("message", "로그아웃되었습니다."));
    }

    @PatchMapping("/me/nickname")
    @Transactional
    public ResponseEntity<?> updateNickname(@Valid @RequestBody NicknameRequest request, Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        String nickname = request.nickname() == null ? "" : request.nickname().trim();
        if (nickname.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of("nickname", List.of("닉네임을 입력해주세요.")));
        }
        UserProfile profile = profileRepository.findByUserId(user.getId()).orElse(null);
        if (profile == null) {
            return ResponseEntity.badRequest().body(Map.of("detail", "프로필이 없습니다."));
        }
        // 본인이 쓰던 닉네임을 그대로 다시 보낼 수 있으므로 그 경우는 통과시킵니다.
        if (!nickname.equals(profile.getNickname()) && profileRepository.existsByNickname(nickname)) {
            return ResponseEntity.badRequest().body(Map.of("nickname", List.of("이미 사용 중인 닉네임입니다.")));
        }
        profile.changeNickname(nickname);
        return ResponseEntity.ok(Map.of("user", userPayloadFactory.of(user)));
    }

    /** 프론트가 FormData 로 파일을 보냅니다. Django 와 같은 필드 이름을 씁니다. */
    @PatchMapping(value = "/me/profile-image",
            consumes = org.springframework.http.MediaType.MULTIPART_FORM_DATA_VALUE)
    @Transactional
    public ResponseEntity<?> updateProfileImageFile(
            @RequestParam("profile_image") org.springframework.web.multipart.MultipartFile file,
            Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        UserProfile profile = profileRepository.findByUserId(user.getId()).orElse(null);
        if (profile == null) {
            return ResponseEntity.badRequest().body(Map.of("detail", "프로필이 없습니다."));
        }
        try {
            profile.changeProfileImage(
                    storageService.upload(file, com.kyb.lifeinframap.storage.service.StorageService.PROFILE_IMAGE_PREFIX));
        } catch (IllegalArgumentException exception) {
            return ResponseEntity.badRequest().body(Map.of("profile_image", List.of(exception.getMessage())));
        }
        return ResponseEntity.ok(Map.of("user", userPayloadFactory.of(user)));
    }

    @PatchMapping("/me/profile-image")
    @Transactional
    public ResponseEntity<?> updateProfileImage(@Valid @RequestBody ProfileImageRequest request,
                                                Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        UserProfile profile = profileRepository.findByUserId(user.getId()).orElse(null);
        if (profile == null) {
            return ResponseEntity.badRequest().body(Map.of("detail", "프로필이 없습니다."));
        }
        // 파일 업로드 자체는 프론트가 저장소에 올리고, 여기서는 키만 받습니다.
        profile.changeProfileImage(request.profileImage());
        return ResponseEntity.ok(Map.of("user", userPayloadFactory.of(user)));
    }

    @GetMapping("/mypage")
    @Transactional(readOnly = true)
    public ResponseEntity<?> mypage(Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        List<Post> authoredPosts = postRepository.findByAuthorIdOrderByCreatedAtDesc(user.getId());
        List<Comment> authoredComments = commentRepository.findByAuthorIdOrderByCreatedAtDesc(user.getId());
        List<Post> likedPostEntities = postLikeRepository.findByUserIdOrderByCreatedAtDesc(user.getId()).stream()
                .map(PostLike::getPost)
                .toList();

        List<User> authors = new ArrayList<>();
        authors.add(user);
        likedPostEntities.forEach(post -> authors.add(post.getAuthor()));
        BoardResponseAssembler.AuthorContext context = assembler.loadAuthors(authors);

        List<Map<String, Object>> posts = new ArrayList<>();
        authoredPosts.forEach(post -> posts.add(assembler.post(post, context, user.getId(), false)));

        List<Map<String, Object>> comments = new ArrayList<>();
        authoredComments.forEach(comment -> comments.add(assembler.comment(comment, context, user.getId(), List.of())));

        List<Map<String, Object>> likedPosts = new ArrayList<>();
        likedPostEntities.forEach(post -> likedPosts.add(assembler.post(post, context, user.getId(), false)));

        List<Map<String, Object>> notifications = notificationRepository
                .findByRecipientIdOrderByCreatedAtDesc(user.getId()).stream()
                .map(this::serializeNotification)
                .toList();
        List<Map<String, Object>> inquiries = inquiryRepository
                .findByAuthorIdOrderByCreatedAtDesc(user.getId()).stream()
                .map(this::serializeInquiry)
                .toList();

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("user", userPayloadFactory.of(user));
        body.put("posts", posts);
        body.put("comments", comments);
        body.put("liked_posts", likedPosts);
        body.put("notifications", notifications);
        body.put("inquiries", inquiries);
        body.put("unread_notification_count", notificationRepository.countByRecipientIdAndReadFalse(user.getId()));
        body.put("inquiry_count", inquiryRepository
                .findByAuthorIdOrderByCreatedAtDesc(user.getId(), PageRequest.of(0, 1)).getTotalElements());
        body.put("penalty", penaltyService.serialize(penaltyService.findCurrent(user.getId())));
        return ResponseEntity.ok(body);
    }

    private Map<String, Object> serializeNotification(Notification notification) {
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

    private Map<String, Object> serializeInquiry(Inquiry inquiry) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("id", inquiry.getId());
        body.put("author", inquiry.getAuthor().getId());
        body.put("author_username", inquiry.getAuthor().getUsername());
        body.put("title", inquiry.getTitle());
        body.put("content", inquiry.getContent());
        body.put("status", inquiry.getStatus());
        body.put("admin_reply", inquiry.getAdminReply());
        body.put("replied_by", inquiry.getRepliedBy() == null ? null : inquiry.getRepliedBy().getId());
        body.put("replied_by_username",
                inquiry.getRepliedBy() == null ? null : inquiry.getRepliedBy().getUsername());
        body.put("replied_at", inquiry.getRepliedAt());
        body.put("created_at", inquiry.getCreatedAt());
        body.put("updated_at", inquiry.getUpdatedAt());
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
