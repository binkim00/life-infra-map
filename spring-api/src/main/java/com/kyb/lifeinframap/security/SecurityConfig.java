package com.kyb.lifeinframap.security;

import java.nio.charset.StandardCharsets;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    /** 기존 Django 사용자의 비밀번호를 그대로 검증하기 위해 씁니다. */
    @Bean
    public PasswordEncoder passwordEncoder() {
        return new DjangoPasswordEncoder();
    }

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http, JwtAuthenticationFilter jwtFilter) throws Exception {
        http
                // 토큰 기반이라 세션과 CSRF 를 쓰지 않습니다.
                .cors(cors -> {})
                .csrf(csrf -> csrf.disable())
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.POST, "/api/auth/login").permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/accounts/signup").permitAll()
                        .requestMatchers("/api/health").permitAll()
                        // `/api/tiers/**` 는 이관 중 Django 계산 결과와 대조하려고 열어 두었다가 닫았습니다.
                        // 열려 있으면 누구나 남의 등급·기여도를 조회할 수 있고,
                        // 프론트는 이 엔드포인트를 쓰지 않습니다(등급은 사용자 응답의 `tier` 로 전달됩니다).
                        // 게시글 목록/상세는 로그인 없이도 볼 수 있습니다. Django 가 AllowAny 였습니다.
                        // 인증 정보가 있으면 필터가 채워 주므로 좋아요 표시 같은 개인화도 그대로 동작합니다.
                        .requestMatchers(HttpMethod.GET, "/api/boards/posts", "/api/boards/posts/*").permitAll()
                        .anyRequest().authenticated())
                // 인증이 없을 때 Spring 기본값은 403 이지만 Django DRF 는 401 을 돌려줍니다.
                // 프론트 axios 인터셉터가 401 에서만 토큰을 지우고 로그인으로 보내므로,
                // 403 으로 두면 토큰이 만료됐을 때 요청이 조용히 실패만 하고 로그인 유도가 안 됩니다.
                .exceptionHandling(handling -> handling
                        .authenticationEntryPoint(unauthorizedEntryPoint()))
                .addFilterBefore(jwtFilter, UsernamePasswordAuthenticationFilter.class);
        return http.build();
    }

    /**
     * 자격증명이 없거나 토큰이 유효하지 않을 때의 응답입니다.
     *
     * 권한이 모자란 경우(로그인은 했지만 남의 글을 수정하는 등)는 각 컨트롤러가 403 을 내려주므로
     * 여기서는 인증 실패만 다룹니다. 본문 형태는 Django `{"detail": ...}` 과 맞춥니다.
     */
    private AuthenticationEntryPoint unauthorizedEntryPoint() {
        return (request, response, exception) -> {
            response.setStatus(HttpStatus.UNAUTHORIZED.value());
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.setHeader(HttpHeaders.WWW_AUTHENTICATE, "Bearer");
            response.getWriter().write("{\"detail\":\"로그인이 필요합니다.\"}");
        };
    }
}
