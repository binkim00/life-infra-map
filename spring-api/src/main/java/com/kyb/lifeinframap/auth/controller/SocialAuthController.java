package com.kyb.lifeinframap.auth.controller;

import com.kyb.lifeinframap.account.domain.User;
import com.kyb.lifeinframap.auth.service.RefreshTokenService;
import com.kyb.lifeinframap.auth.service.SocialLoginTicketService;
import com.kyb.lifeinframap.auth.service.SocialOAuthSettings;
import com.kyb.lifeinframap.security.JwtService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import java.net.URI;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriComponentsBuilder;

@RestController
@RequestMapping("/api/auth/social")
public class SocialAuthController {
    private final SocialOAuthSettings settings;
    private final SocialLoginTicketService tickets;
    private final RefreshTokenService refreshTokens;
    private final JwtService jwt;

    public SocialAuthController(SocialOAuthSettings settings, SocialLoginTicketService tickets,
            RefreshTokenService refreshTokens, JwtService jwt) {
        this.settings = settings;
        this.tickets = tickets;
        this.refreshTokens = refreshTokens;
        this.jwt = jwt;
    }

    @GetMapping("/providers")
    public Map<String, Object> providers() { return Map.of("providers", settings.providers()); }

    @GetMapping("/{provider}/start")
    public ResponseEntity<?> start(@PathVariable String provider, @RequestParam String client,
            @RequestParam String nonce, HttpServletRequest request) {
        if (!settings.available(provider) || (!"web".equals(client) && !"mobile".equals(client))
                || !nonce.matches("[A-Za-z0-9_-]{20,100}")) {
            return ResponseEntity.badRequest().body(Map.of("detail", "소셜 로그인 요청이 올바르지 않습니다."));
        }
        // The OAuth callback uses the public host. Move there before creating
        // the temporary session; browser cookies are scoped to their host.
        if (!URI.create(settings.publicBaseUrl()).getHost().equalsIgnoreCase(request.getServerName())) {
            URI canonicalStart = UriComponentsBuilder.fromUriString(settings.publicBaseUrl())
                    .path("/spring/api/auth/social/{provider}/start")
                    .queryParam("client", client)
                    .queryParam("nonce", nonce)
                    .buildAndExpand(provider).toUri();
            return ResponseEntity.status(HttpStatus.FOUND).location(canonicalStart).build();
        }
        HttpSession session = request.getSession(true);
        request.changeSessionId();
        session.setMaxInactiveInterval(300);
        session.setAttribute("social_client", client);
        session.setAttribute("social_nonce", nonce);
        return ResponseEntity.status(HttpStatus.FOUND)
                .location(URI.create(settings.publicBaseUrl() + "/spring/api/oauth2/authorization/" + provider))
                .build();
    }

    public record ExchangeRequest(String ticket) {}

    @PostMapping("/exchange")
    public ResponseEntity<?> exchange(@RequestBody ExchangeRequest request) {
        User user = tickets.consume(request.ticket());
        if (user == null) return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body(Map.of("detail", "로그인 유효 시간이 지났습니다. 다시 시도해 주세요."));
        return ResponseEntity.ok(Map.of(
                "access_token", jwt.issueAccessToken(user.getId(), user.getUsername()),
                "refresh_token", refreshTokens.issue(user),
                "token_type", "Bearer", "expires_in", jwt.getAccessTokenSeconds(),
                "user", Map.of("id", user.getId(), "username", user.getUsername(),
                        "email", user.getEmail(), "is_staff", user.isStaff())));
    }
}
