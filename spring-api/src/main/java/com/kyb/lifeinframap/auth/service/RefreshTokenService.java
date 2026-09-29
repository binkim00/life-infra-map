package com.kyb.lifeinframap.auth.service;

import com.kyb.lifeinframap.account.domain.User;
import com.kyb.lifeinframap.account.repository.UserRepository;
import com.kyb.lifeinframap.auth.domain.RefreshSession;
import com.kyb.lifeinframap.auth.repository.RefreshSessionRepository;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.OffsetDateTime;
import java.util.Base64;
import java.util.HexFormat;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RefreshTokenService {
    private final RefreshSessionRepository sessions;
    private final UserRepository users;
    private final SecureRandom random = new SecureRandom();
    private final int ttlDays;

    public RefreshTokenService(RefreshSessionRepository sessions, UserRepository users,
            @Value("${app.jwt.refresh-token-days:30}") int ttlDays) {
        this.sessions = sessions;
        this.users = users;
        this.ttlDays = ttlDays;
    }

    @Transactional
    public String issue(User user) {
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        String token = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        sessions.save(RefreshSession.create(user.getId(), hash(token), OffsetDateTime.now().plusDays(ttlDays)));
        return token;
    }

    @Transactional
    public RotatedToken rotate(String token) {
        if (token == null || token.length() < 40 || token.length() > 100) return null;
        RefreshSession session = sessions.lockByTokenHash(hash(token)).orElse(null);
        if (session == null || !session.isActive(OffsetDateTime.now())) return null;
        User user = users.findById(session.getUserId()).orElse(null);
        if (user == null || !user.isActive()) return null;
        session.revoke(OffsetDateTime.now());
        return new RotatedToken(user, issue(user));
    }

    @Transactional
    public void revoke(String token) {
        if (token == null || token.length() < 40 || token.length() > 100) return;
        sessions.lockByTokenHash(hash(token)).ifPresent(session -> session.revoke(OffsetDateTime.now()));
    }

    private String hash(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 unavailable", exception);
        }
    }

    public record RotatedToken(User user, String refreshToken) {}
}
