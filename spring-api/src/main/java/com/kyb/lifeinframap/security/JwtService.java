package com.kyb.lifeinframap.security;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;
import javax.crypto.SecretKey;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

/**
 * 서비스 사이에서 공유하는 액세스 토큰을 발급하고 검증합니다.
 *
 * Django 쪽 recommendations 서비스도 같은 비밀키로 이 토큰을 검증하므로,
 * 클레임 이름을 바꾸면 양쪽을 함께 고쳐야 합니다.
 */
@Service
public class JwtService {

    private final SecretKey key;
    private final Duration accessTokenTtl;

    public JwtService(
            @Value("${app.jwt.secret}") String secret,
            @Value("${app.jwt.access-token-minutes}") long accessTokenMinutes) {
        byte[] secretBytes = secret.getBytes(StandardCharsets.UTF_8);
        if (secretBytes.length < 32) {
            throw new IllegalStateException("app.jwt.secret 은 32바이트 이상이어야 합니다.");
        }
        this.key = Keys.hmacShaKeyFor(secretBytes);
        this.accessTokenTtl = Duration.ofMinutes(accessTokenMinutes);
    }

    public String issueAccessToken(Integer userId, String username) {
        Instant now = Instant.now();
        return Jwts.builder()
                .subject(String.valueOf(userId))
                .claim("username", username)
                .issuedAt(Date.from(now))
                .expiration(Date.from(now.plus(accessTokenTtl)))
                // 키 길이에 따라 알고리즘이 달라지면 Django 와 호환되지 않는다.
                // 두 서비스의 공유 토큰 계약은 HS256 으로 고정한다.
                .signWith(key, Jwts.SIG.HS256)
                .compact();
    }

    public Claims parse(String token) {
        return Jwts.parser()
                .verifyWith(key)
                .build()
                .parseSignedClaims(token)
                .getPayload();
    }

    public long getAccessTokenSeconds() {
        return accessTokenTtl.toSeconds();
    }
}
