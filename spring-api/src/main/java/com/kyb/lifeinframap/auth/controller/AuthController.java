package com.kyb.lifeinframap.auth.controller;

import com.kyb.lifeinframap.auth.dto.*;

import com.kyb.lifeinframap.account.domain.User;
import com.kyb.lifeinframap.account.repository.UserRepository;
import com.kyb.lifeinframap.security.JwtService;
import com.kyb.lifeinframap.auth.service.RefreshTokenService;
import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import java.time.OffsetDateTime;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class AuthController {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtService jwtService;
    private final RefreshTokenService refreshTokens;

    public AuthController(UserRepository userRepository, PasswordEncoder passwordEncoder, JwtService jwtService,
            RefreshTokenService refreshTokens) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
        this.jwtService = jwtService;
        this.refreshTokens = refreshTokens;
    }


    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("message", "life-infra-map api is working");
    }

    @PostMapping("/auth/login")
    @Transactional
    public ResponseEntity<?> login(@Valid @RequestBody LoginRequest request) {
        // 아이디가 없을 때와 비밀번호가 틀렸을 때를 구분해 알려주지 않습니다.
        User user = userRepository.findByUsername(request.username()).orElse(null);
        if (user == null || !user.isActive() || !passwordEncoder.matches(request.password(), user.getPassword())) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .body(Map.of("detail", "아이디 또는 비밀번호가 올바르지 않습니다."));
        }

        user.markLoggedIn(OffsetDateTime.now());

        return ResponseEntity.ok(Map.of(
                "access_token", jwtService.issueAccessToken(user.getId(), user.getUsername()),
                "refresh_token", refreshTokens.issue(user),
                "token_type", "Bearer",
                "expires_in", jwtService.getAccessTokenSeconds(),
                "user", Map.of(
                        "id", user.getId(),
                        "username", user.getUsername(),
                        "email", user.getEmail(),
                        "is_staff", user.isStaff())));
    }

    public record RefreshRequest(@JsonProperty("refresh_token") String refreshToken) {}

    @PostMapping("/auth/refresh")
    public ResponseEntity<?> refresh(@RequestBody RefreshRequest request) {
        RefreshTokenService.RotatedToken rotated = refreshTokens.rotate(request.refreshToken());
        if (rotated == null) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(Map.of("detail", "다시 로그인해 주세요."));
        }
        User user = rotated.user();
        return ResponseEntity.ok(Map.of(
                "access_token", jwtService.issueAccessToken(user.getId(), user.getUsername()),
                "refresh_token", rotated.refreshToken(),
                "token_type", "Bearer", "expires_in", jwtService.getAccessTokenSeconds(),
                "user", Map.of("id", user.getId(), "username", user.getUsername(),
                        "email", user.getEmail(), "is_staff", user.isStaff())));
    }

    @PostMapping("/auth/logout")
    public ResponseEntity<?> logout(@RequestBody RefreshRequest request) {
        refreshTokens.revoke(request.refreshToken());
        return ResponseEntity.ok(Map.of("message", "로그아웃했습니다."));
    }
}
