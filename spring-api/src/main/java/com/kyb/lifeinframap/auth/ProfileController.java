package com.kyb.lifeinframap.auth;

import com.kyb.lifeinframap.account.User;
import com.kyb.lifeinframap.account.UserProfile;
import com.kyb.lifeinframap.account.UserProfileRepository;
import com.kyb.lifeinframap.account.UserRepository;
import com.kyb.lifeinframap.board.*;
import com.kyb.lifeinframap.tier.ContributionService;
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
 * 프로필과 마이페이지입니다. Django `accounts/views.py` 의 나머지 엔드포인트를 옮겼습니다.
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
    private final CommentRepository commentRepository;
    private final NotificationRepository notificationRepository;
    private final InquiryRepository inquiryRepository;
    private final PenaltyService penaltyService;
    private final BoardResponseAssembler assembler;

    public ProfileController(
            UserRepository userRepository,
            UserProfileRepository profileRepository,
            ContributionService contributionService,
            PostRepository postRepository,
            CommentRepository commentRepository,
            NotificationRepository notificationRepository,
            InquiryRepository inquiryRepository,
            PenaltyService penaltyService,
            BoardResponseAssembler assembler) {
        this.userRepository = userRepository;
        this.profileRepository = profileRepository;
        this.contributionService = contributionService;
        this.postRepository = postRepository;
        this.commentRepository = commentRepository;
        this.notificationRepository = notificationRepository;
        this.inquiryRepository = inquiryRepository;
        this.penaltyService = penaltyService;
        this.assembler = assembler;
    }

    public record NicknameRequest(@NotBlank String nickname) {
    }

    public record ProfileImageRequest(String profileImage) {
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
    public ResponseEntity<?> updateNickname(@RequestBody NicknameRequest request, Authentication authentication) {
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
        return ResponseEntity.ok(Map.of("user", userPayload(user)));
    }

    @PatchMapping("/me/profile-image")
    @Transactional
    public ResponseEntity<?> updateProfileImage(@RequestBody ProfileImageRequest request,
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
        return ResponseEntity.ok(Map.of("user", userPayload(user)));
    }

    @GetMapping("/mypage")
    @Transactional(readOnly = true)
    public ResponseEntity<?> mypage(Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        BoardResponseAssembler.AuthorContext context = assembler.loadAuthors(List.of(user));

        List<Map<String, Object>> posts = new ArrayList<>();
        postRepository.findAll().stream()
                .filter(post -> post.getAuthor().getId().equals(user.getId()))
                .forEach(post -> posts.add(assembler.post(post, context, user.getId(), false)));

        List<Map<String, Object>> comments = new ArrayList<>();
        commentRepository.findAll().stream()
                .filter(comment -> comment.getAuthor().getId().equals(user.getId()))
                .forEach(comment -> comments.add(assembler.comment(comment, context, user.getId(), List.of())));

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("user", userPayload(user));
        body.put("posts", posts);
        body.put("comments", comments);
        body.put("unread_notification_count", notificationRepository.countByRecipientIdAndReadFalse(user.getId()));
        body.put("inquiry_count", inquiryRepository
                .findByAuthorIdOrderByCreatedAtDesc(user.getId(), PageRequest.of(0, 1)).getTotalElements());
        body.put("penalty", penaltyService.serialize(penaltyService.findCurrent(user.getId())));
        return ResponseEntity.ok(body);
    }

    /** Django `UserSerializer` 와 같은 필드로 맞춥니다. */
    private Map<String, Object> userPayload(User user) {
        UserProfile profile = profileRepository.findByUserId(user.getId()).orElse(null);
        ContributionService.TierInfo tier = contributionService.getTierInfo(user.getId(), user.isStaff());

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("id", user.getId());
        payload.put("username", user.getUsername());
        payload.put("nickname", profile == null ? user.getUsername() : profile.getNickname());
        payload.put("profile_image_url", assembler.fileUrl(profile == null ? null : profile.getProfileImage()));
        payload.put("email", user.getEmail());
        payload.put("is_staff", user.isStaff());
        payload.put("score", tier.score());
        payload.put("contribution", tier.contribution());
        payload.put("tier", tier.tier());
        payload.put("tier_label", tier.tierLabel());
        payload.put("tier_color", tier.tierColor());
        payload.put("nickname_color", tier.nicknameColor());
        return payload;
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
