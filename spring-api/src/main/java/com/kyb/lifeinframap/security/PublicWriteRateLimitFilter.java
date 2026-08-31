package com.kyb.lifeinframap.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/** 로그인·회원가입 무차별 요청을 인스턴스별로 제한합니다. */
@Component
public class PublicWriteRateLimitFilter extends OncePerRequestFilter {

    private final Map<String, Deque<Long>> attempts = new ConcurrentHashMap<>();
    private final int loginLimit;
    private final int signupLimit;

    public PublicWriteRateLimitFilter(
            @Value("${app.rate-limit.login-per-minute:20}") int loginLimit,
            @Value("${app.rate-limit.signup-per-minute:5}") int signupLimit) {
        this.loginLimit = loginLimit;
        this.signupLimit = signupLimit;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        if (!"POST".equalsIgnoreCase(request.getMethod())) {
            return true;
        }
        String path = request.getRequestURI();
        return !"/api/auth/login".equals(path) && !"/api/accounts/signup".equals(path);
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String path = request.getRequestURI();
        int limit = "/api/auth/login".equals(path) ? loginLimit : signupLimit;
        String key = path + ":" + request.getRemoteAddr();
        long now = Instant.now().toEpochMilli();
        long cutoff = now - 60_000;
        Deque<Long> timestamps = attempts.computeIfAbsent(key, ignored -> new ArrayDeque<>());
        boolean allowed;
        synchronized (timestamps) {
            while (!timestamps.isEmpty() && timestamps.peekFirst() < cutoff) {
                timestamps.removeFirst();
            }
            allowed = timestamps.size() < limit;
            if (allowed) {
                timestamps.addLast(now);
            }
        }
        if (!allowed) {
            response.setStatus(HttpStatus.TOO_MANY_REQUESTS.value());
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.getWriter().write("{\"detail\":\"요청이 너무 많습니다. 잠시 후 다시 시도해주세요.\"}");
            return;
        }
        chain.doFilter(request, response);
    }
}
