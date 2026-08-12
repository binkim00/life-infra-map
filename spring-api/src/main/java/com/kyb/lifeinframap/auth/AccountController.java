package com.kyb.lifeinframap.auth;

import com.kyb.lifeinframap.account.User;
import com.kyb.lifeinframap.account.UserProfile;
import com.kyb.lifeinframap.account.UserProfileRepository;
import com.kyb.lifeinframap.account.UserRepository;
import com.kyb.lifeinframap.security.JwtService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 회원가입, 비밀번호 변경, 내 정보처럼 다른 도메인에 기대지 않는 계정 기능입니다.
 *
 * 등급/기여도는 boards 활동과 recommendations 제보를 함께 봐야 계산되므로
 * 여기서 내려주지 않습니다. 그 부분은 아직 Django 가 담당합니다.
 */
@RestController
@RequestMapping("/api/accounts")
public class AccountController {

    private final UserRepository userRepository;
    private final UserProfileRepository profileRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtService jwtService;
    private final com.kyb.lifeinframap.storage.StorageService storageService;
    private final com.kyb.lifeinframap.account.UserPayloadFactory userPayloadFactory;

    public AccountController(
            UserRepository userRepository,
            UserProfileRepository profileRepository,
            PasswordEncoder passwordEncoder,
            JwtService jwtService,
            com.kyb.lifeinframap.storage.StorageService storageService,
            com.kyb.lifeinframap.account.UserPayloadFactory userPayloadFactory) {
        this.userRepository = userRepository;
        this.profileRepository = profileRepository;
        this.passwordEncoder = passwordEncoder;
        this.jwtService = jwtService;
        this.storageService = storageService;
        this.userPayloadFactory = userPayloadFactory;
    }

    public record SignupRequest(
            @NotBlank @Size(max = 150) String username,
            @NotBlank @Size(max = 50) String nickname,
            String email,
            @NotBlank @Size(min = 8) String password,
            @NotBlank @Size(min = 8) String passwordConfirm) {
    }

    public record PasswordChangeRequest(
            @NotBlank String currentPassword,
            @NotBlank @Size(min = 8) String newPassword,
            @NotBlank @Size(min = 8) String newPasswordConfirm) {
    }

    /**
     * 프로필 사진을 함께 올리는 회원가입입니다.
     *
     * 프론트가 FormData 로 보내므로 필드 이름은 Django 와 같은 스네이크 표기를 씁니다.
     */
    @PostMapping(value = "/signup", consumes = org.springframework.http.MediaType.MULTIPART_FORM_DATA_VALUE)
    @Transactional
    public ResponseEntity<?> signupMultipart(
            @RequestParam String username,
            @RequestParam String nickname,
            @RequestParam(required = false) String email,
            @RequestParam String password,
            @RequestParam("password_confirm") String passwordConfirm,
            @RequestParam(value = "profile_image", required = false)
            org.springframework.web.multipart.MultipartFile profileImage) {

        String imageKey;
        try {
            imageKey = storageService.upload(profileImage, com.kyb.lifeinframap.storage.StorageService.PROFILE_IMAGE_PREFIX);
        } catch (IllegalArgumentException exception) {
            return badRequest("profile_image", exception.getMessage());
        }

        return createAccount(new SignupRequest(username, nickname, email, password, passwordConfirm), imageKey);
    }

    @PostMapping("/signup")
    @Transactional
    public ResponseEntity<?> signup(@Valid @RequestBody SignupRequest request) {
        return createAccount(request, null);
    }

    private ResponseEntity<?> createAccount(SignupRequest request, String profileImageKey) {
        if (!request.password().equals(request.passwordConfirm())) {
            return badRequest("passwordConfirm", "비밀번호가 일치하지 않습니다.");
        }
        if (userRepository.findByUsername(request.username()).isPresent()) {
            return badRequest("username", "이미 사용 중인 아이디입니다.");
        }

        String nickname = request.nickname().trim();
        if (nickname.isEmpty()) {
            return badRequest("nickname", "닉네임을 입력해주세요.");
        }
        if (profileRepository.existsByNickname(nickname)) {
            return badRequest("nickname", "이미 사용 중인 닉네임입니다.");
        }

        User user = userRepository.save(
                User.create(request.username(), request.email(), passwordEncoder.encode(request.password())));
        UserProfile profile = new UserProfile(user, nickname);
        if (profileImageKey != null) {
            profile.changeProfileImage(profileImageKey);
        }
        profileRepository.save(profile);

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("message", "회원가입이 완료되었습니다.");
        body.put("access_token", jwtService.issueAccessToken(user.getId(), user.getUsername()));
        body.put("token_type", "Bearer");
        body.put("expires_in", jwtService.getAccessTokenSeconds());
        body.put("user", userPayloadFactory.of(user, nickname, profileImageKey));
        return ResponseEntity.status(HttpStatus.CREATED).body(body);
    }

    @PatchMapping("/me/password")
    @Transactional
    public ResponseEntity<?> changePassword(
            @Valid @RequestBody PasswordChangeRequest request,
            org.springframework.security.core.Authentication authentication) {
        if (!request.newPassword().equals(request.newPasswordConfirm())) {
            return badRequest("newPasswordConfirm", "새 비밀번호가 일치하지 않습니다.");
        }

        User user = currentUser(authentication);
        if (user == null) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(Map.of("detail", "인증이 필요합니다."));
        }
        if (!passwordEncoder.matches(request.currentPassword(), user.getPassword())) {
            return badRequest("currentPassword", "현재 비밀번호가 올바르지 않습니다.");
        }

        // Django 형식으로 저장하므로 Django 쪽 로그인에서도 새 비밀번호가 그대로 통합니다.
        user.changePassword(passwordEncoder.encode(request.newPassword()));

        return ResponseEntity.ok(Map.of("message", "비밀번호가 변경되었습니다."));
    }

    @GetMapping("/me")
    public ResponseEntity<?> me(org.springframework.security.core.Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(Map.of("detail", "인증이 필요합니다."));
        }
        return ResponseEntity.ok(userPayloadFactory.of(user));
    }

    private User currentUser(org.springframework.security.core.Authentication authentication) {
        if (authentication == null || authentication.getName() == null) {
            return null;
        }
        try {
            return userRepository.findById(Integer.valueOf(authentication.getName())).orElse(null);
        } catch (NumberFormatException exception) {
            return null;
        }
    }


    private ResponseEntity<Map<String, Object>> badRequest(String field, String message) {
        return ResponseEntity.badRequest().body(Map.of(field, java.util.List.of(message)));
    }
}
