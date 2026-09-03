package com.kyb.lifeinframap;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.kyb.lifeinframap.account.domain.User;
import com.kyb.lifeinframap.support.ApiTestBase;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MvcResult;

/**
 * 인증·계정 API의 Spring 이관 결과를 확인합니다.
 *
 * 프론트가 응답의 `access_token`, `token_type`, `user.nickname` 을 그대로 읽으므로
 * 상태 코드만이 아니라 응답 형태도 함께 검증합니다.
 */
class AuthApiTest extends ApiTestBase {

    @Autowired
    private PasswordEncoder passwordEncoder;

    @Test
    @DisplayName("health 는 인증 없이 열려 있다")
    void healthIsPublic() throws Exception {
        mockMvc.perform(get("/api/health"))
                .andExpect(status().isOk());
    }

    @Test
    @DisplayName("로그인하면 Bearer 토큰을 돌려준다")
    void loginReturnsBearerToken() throws Exception {
        String username = "logintest_" + System.nanoTime();
        User user = User.create(username, username + "@test.dev", passwordEncoder.encode("testpass1234"));
        userRepository.save(user);
        profileRepository.save(new com.kyb.lifeinframap.account.domain.UserProfile(user, "로그인테스트"));

        MvcResult result = mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"%s","password":"testpass1234"}
                                """.formatted(username)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.access_token").exists())
                .andExpect(jsonPath("$.token_type").value("Bearer"))
                .andExpect(jsonPath("$.user.username").value(username))
                .andReturn();

        String token = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("access_token").asText();
        String header = new String(
                Base64.getUrlDecoder().decode(token.substring(0, token.indexOf('.'))),
                StandardCharsets.UTF_8);
        assertThat(objectMapper.readTree(header).get("alg").asText()).isEqualTo("HS256");
    }

    @Test
    @DisplayName("비밀번호가 틀리면 401 이고 토큰을 주지 않는다")
    void loginRejectsWrongPassword() throws Exception {
        String username = "loginfail_" + System.nanoTime();
        User user = User.create(username, username + "@test.dev", passwordEncoder.encode("testpass1234"));
        userRepository.save(user);
        profileRepository.save(new com.kyb.lifeinframap.account.domain.UserProfile(user, "실패테스트"));

        mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"%s","password":"wrongpassword"}
                                """.formatted(username)))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.access_token").doesNotExist())
                .andExpect(jsonPath("$.detail").exists());
    }

    @Test
    @DisplayName("없는 사용자도 같은 401 로 응답한다 (계정 존재 여부를 알려주지 않는다)")
    void loginRejectsUnknownUserWithSameResponse() throws Exception {
        mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"nosuchuser_%d","password":"whatever1234"}
                                """.formatted(System.nanoTime())))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.detail").exists());
    }

    @Test
    @DisplayName("내 정보는 토큰이 없으면 401 이다")
    void meRequiresToken() throws Exception {
        mockMvc.perform(get("/api/accounts/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("토큰이 위조되면 401 이다")
    void meRejectsTamperedToken() throws Exception {
        User user = createUser();
        String tampered = bearer(user) + "x";

        mockMvc.perform(get("/api/accounts/me").header("Authorization", tampered))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("내 정보는 Django UserSerializer 와 같은 필드를 돌려준다")
    void meReturnsDjangoShape() throws Exception {
        User user = createUser();

        mockMvc.perform(get("/api/accounts/me").header("Authorization", bearer(user)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(user.getId()))
                .andExpect(jsonPath("$.username").value(user.getUsername()))
                .andExpect(jsonPath("$.nickname").exists());
    }

    /**
     * Django `accounts/tests.py` 의 `test_user_serializer_response_contains_contribution_and_nickname_color`
     * 를 대체합니다.
     *
     * 프론트가 헤더 아바타와 등급 배지에 이 값들을 씁니다. 하나라도 빠지면 배지가 비어 보입니다.
     * 기여도가 0 인 새 사용자는 `iron` 이어야 합니다.
     */
    @Test
    @DisplayName("내 정보에 기여도·등급·닉네임 색이 함께 온다")
    void meIncludesContributionAndTier() throws Exception {
        User user = createUser();

        mockMvc.perform(get("/api/accounts/me").header("Authorization", bearer(user)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.contribution").value(0))
                .andExpect(jsonPath("$.score").value(0))
                .andExpect(jsonPath("$.tier").value("iron"))
                .andExpect(jsonPath("$.tier_label").exists())
                .andExpect(jsonPath("$.tier_color").exists())
                .andExpect(jsonPath("$.nickname_color").exists())
                .andExpect(jsonPath("$.is_staff").value(false));
    }

    @Test
    @DisplayName("가입 직후 응답에도 등급 정보가 들어 있다")
    void signupResponseIncludesTier() throws Exception {
        String username = "signuptier_" + System.nanoTime();

        // 가입 직후 헤더 아바타와 등급 배지가 비어 보이는 문제가 있어 응답을 통일했습니다.
        mockMvc.perform(post("/api/accounts/signup")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"%s","nickname":"등급확인%d","email":"s@test.dev",
                                 "password":"testpass1234","passwordConfirm":"testpass1234"}
                                """.formatted(username, System.nanoTime() % 100000)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.user.tier").value("iron"))
                .andExpect(jsonPath("$.user.nickname_color").exists())
                .andExpect(jsonPath("$.user.profile_image_url").exists());
    }

    @Test
    @DisplayName("회원가입은 인증 없이 되고 가입 즉시 토큰을 준다")
    void signupIsPublicAndReturnsToken() throws Exception {
        String username = "signup_" + System.nanoTime();

        mockMvc.perform(post("/api/accounts/signup")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"%s","nickname":"가입테스트%d","email":"s@test.dev",
                                 "password":"testpass1234","passwordConfirm":"testpass1234"}
                                """.formatted(username, System.nanoTime() % 100000)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.access_token").exists())
                .andExpect(jsonPath("$.user.username").value(username));

        assertThat(userRepository.findByUsername(username)).isPresent();
    }

    @Test
    @DisplayName("비밀번호 확인이 다르면 가입되지 않는다")
    void signupRejectsMismatchedConfirm() throws Exception {
        String username = "signupbad_" + System.nanoTime();

        mockMvc.perform(post("/api/accounts/signup")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"%s","nickname":"불일치%d","email":"s@test.dev",
                                 "password":"testpass1234","passwordConfirm":"differentpass"}
                                """.formatted(username, System.nanoTime() % 100000)))
                .andExpect(status().isBadRequest());

        assertThat(userRepository.findByUsername(username)).isEmpty();
    }

    // ---------- 계정 수정 ----------
    //
    // 비밀번호 변경·닉네임·프로필사진·마이페이지·로그아웃의 회귀를 검증합니다.

    @Test
    @DisplayName("현재 비밀번호가 맞으면 변경된다")
    void changesPassword() throws Exception {
        String username = "pwchange_" + System.nanoTime();
        User user = User.create(username, username + "@test.dev", passwordEncoder.encode("oldpass1234"));
        userRepository.save(user);
        profileRepository.save(new com.kyb.lifeinframap.account.domain.UserProfile(user, "비번변경" + System.nanoTime()));

        mockMvc.perform(patch("/api/accounts/me/password")
                        .header("Authorization", bearer(user))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"currentPassword":"oldpass1234","newPassword":"newpass1234",
                                 "newPasswordConfirm":"newpass1234"}
                                """))
                .andExpect(status().isOk());

        // 바뀐 비밀번호로 로그인되어야 합니다.
        mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"%s","password":"newpass1234"}
                                """.formatted(username)))
                .andExpect(status().isOk());
    }

    @Test
    @DisplayName("현재 비밀번호가 틀리면 변경되지 않는다")
    void rejectsPasswordChangeWithWrongCurrent() throws Exception {
        String username = "pwfail_" + System.nanoTime();
        User user = User.create(username, username + "@test.dev", passwordEncoder.encode("oldpass1234"));
        userRepository.save(user);
        profileRepository.save(new com.kyb.lifeinframap.account.domain.UserProfile(user, "비번실패" + System.nanoTime()));

        mockMvc.perform(patch("/api/accounts/me/password")
                        .header("Authorization", bearer(user))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"currentPassword":"wrongpass","newPassword":"newpass1234",
                                 "newPasswordConfirm":"newpass1234"}
                                """))
                .andExpect(status().isBadRequest());

        // 기존 비밀번호가 그대로여야 합니다.
        mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"%s","password":"oldpass1234"}
                                """.formatted(username)))
                .andExpect(status().isOk());
    }

    @Test
    @DisplayName("새 비밀번호 확인이 다르면 변경되지 않는다")
    void rejectsPasswordChangeWithMismatchedConfirm() throws Exception {
        User user = createUser();

        mockMvc.perform(patch("/api/accounts/me/password")
                        .header("Authorization", bearer(user))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"currentPassword":"whatever1234","newPassword":"newpass1234",
                                 "newPasswordConfirm":"different1234"}
                                """))
                .andExpect(status().isBadRequest());
    }

    @Test
    @DisplayName("닉네임을 바꿀 수 있다")
    void changesNickname() throws Exception {
        User user = createUser();
        String nickname = "새닉네임" + System.nanoTime();

        mockMvc.perform(patch("/api/accounts/me/nickname")
                        .header("Authorization", bearer(user))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"nickname":"%s"}
                                """.formatted(nickname)))
                .andExpect(status().isOk());

        mockMvc.perform(get("/api/accounts/me").header("Authorization", bearer(user)))
                .andExpect(jsonPath("$.nickname").value(nickname));
    }

    @Test
    @DisplayName("이미 쓰는 닉네임으로는 바꿀 수 없다")
    void rejectsDuplicateNickname() throws Exception {
        User first = createUser();
        User second = createUser();

        MvcResult existing = mockMvc.perform(get("/api/accounts/me")
                        .header("Authorization", bearer(first)))
                .andReturn();
        String taken = objectMapper.readTree(existing.getResponse().getContentAsString())
                .get("nickname").asText();

        mockMvc.perform(patch("/api/accounts/me/nickname")
                        .header("Authorization", bearer(second))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"nickname":"%s"}
                                """.formatted(taken)))
                .andExpect(status().isBadRequest());
    }

    @Test
    @DisplayName("프로필 사진 키를 JSON 으로도 바꿀 수 있다")
    void changesProfileImageByKey() throws Exception {
        User user = createUser();

        // multipart 경로는 저장소(MinIO)가 필요해 여기서는 JSON 경로만 확인합니다.
        mockMvc.perform(patch("/api/accounts/me/profile-image")
                        .header("Authorization", bearer(user))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"profileImage":"profile_images/test.png"}
                                """))
                .andExpect(status().isOk());
    }

    @Test
    @DisplayName("마이페이지는 로그인이 필요하다")
    void mypageRequiresAuth() throws Exception {
        mockMvc.perform(get("/api/accounts/mypage"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("마이페이지를 조회할 수 있다")
    void returnsMypage() throws Exception {
        User user = createUser();

        mockMvc.perform(get("/api/accounts/mypage").header("Authorization", bearer(user)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.user.date_joined").exists())
                .andExpect(jsonPath("$.posts").isArray())
                .andExpect(jsonPath("$.comments").isArray())
                .andExpect(jsonPath("$.liked_posts").isArray())
                .andExpect(jsonPath("$.notifications").isArray())
                .andExpect(jsonPath("$.inquiries").isArray());
    }

    @Test
    @DisplayName("로그아웃은 로그인 상태에서 동작한다")
    void logout() throws Exception {
        User user = createUser();

        mockMvc.perform(post("/api/accounts/logout").header("Authorization", bearer(user)))
                .andExpect(status().isOk());
    }

    @Test
    @DisplayName("이미 있는 아이디로는 가입되지 않는다")
    void signupRejectsDuplicateUsername() throws Exception {
        User existing = createUser();

        mockMvc.perform(post("/api/accounts/signup")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"%s","nickname":"중복%d","email":"s@test.dev",
                                 "password":"testpass1234","passwordConfirm":"testpass1234"}
                                """.formatted(existing.getUsername(), System.nanoTime() % 100000)))
                .andExpect(status().isBadRequest());
    }
}
