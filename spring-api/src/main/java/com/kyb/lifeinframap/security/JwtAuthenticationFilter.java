package com.kyb.lifeinframap.security;

import com.kyb.lifeinframap.account.repository.UserRepository;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.List;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * `Authorization: Bearer <token>` 를 확인해 인증 정보를 채웁니다.
 *
 * 토큰의 `sub` 는 사용자 id 이며, 컨트롤러는 `authentication.getName()` 으로 이 값을 받습니다.
 * Django 쪽 `SharedJWTAuthentication` 과 같은 규칙입니다.
 */
@Component
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    private static final String PREFIX = "Bearer ";

    private final JwtService jwtService;
    private final UserRepository userRepository;

    public JwtAuthenticationFilter(JwtService jwtService, UserRepository userRepository) {
        this.jwtService = jwtService;
        this.userRepository = userRepository;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {

        String header = request.getHeader("Authorization");
        if (header != null && header.startsWith(PREFIX)
                && SecurityContextHolder.getContext().getAuthentication() == null) {
            try {
                Claims claims = jwtService.parse(header.substring(PREFIX.length()).trim());
                int userId = Integer.parseInt(claims.getSubject());
                if (userRepository.findById(userId).filter(user -> user.isActive()).isEmpty()) {
                    SecurityContextHolder.clearContext();
                    chain.doFilter(request, response);
                    return;
                }
                UsernamePasswordAuthenticationToken authentication =
                        new UsernamePasswordAuthenticationToken(String.valueOf(userId), null, List.of());
                authentication.setDetails(claims.get("username"));
                SecurityContextHolder.getContext().setAuthentication(authentication);
            } catch (JwtException | IllegalArgumentException exception) {
                // 토큰이 잘못되면 인증 없이 진행하고, 접근 제어는 SecurityConfig 가 판단합니다.
                SecurityContextHolder.clearContext();
            }
        }

        chain.doFilter(request, response);
    }
}
