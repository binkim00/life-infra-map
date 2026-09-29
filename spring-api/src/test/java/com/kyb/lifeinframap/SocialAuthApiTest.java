package com.kyb.lifeinframap;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.kyb.lifeinframap.account.domain.User;
import com.kyb.lifeinframap.auth.service.SocialLoginTicketService;
import com.kyb.lifeinframap.auth.service.SocialOAuthSuccessHandler;
import com.kyb.lifeinframap.support.ApiTestBase;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.core.user.OAuth2User;

class SocialAuthApiTest extends ApiTestBase {
    @Autowired SocialLoginTicketService tickets;

    @Test
    void disabledProvidersAreHiddenAndCannotStart() throws Exception {
        mockMvc.perform(get("/api/auth/social/providers"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.providers").isEmpty());
        mockMvc.perform(get("/api/auth/social/google/start")
                        .param("client", "web").param("nonce", "12345678901234567890"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void ticketCanOnlyBeExchangedOnce() throws Exception {
        User user = createUser();
        String ticket = tickets.issue(user);
        String body = "{\"ticket\":\"" + ticket + "\"}";
        mockMvc.perform(post("/api/auth/social/exchange")
                        .contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isOk()).andExpect(jsonPath("$.access_token").isString())
                .andExpect(jsonPath("$.refresh_token").isString())
                .andExpect(jsonPath("$.user.id").value(user.getId()));
        mockMvc.perform(post("/api/auth/social/exchange")
                        .contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void verifiedClaimIsRequiredForAccountLinking() {
        OAuth2User kakao = mock(OAuth2User.class);
        when(kakao.getAttributes()).thenReturn(Map.of("id", 17, "kakao_account", Map.of(
                "email", "existing@example.com", "is_email_verified", true, "is_email_valid", false)));
        assertThat(SocialOAuthSuccessHandler.profile("kakao", kakao).verified()).isFalse();
        OAuth2User google = mock(OAuth2User.class);
        when(google.getAttributes()).thenReturn(Map.of("sub", "g1", "email", "existing@example.com",
                "email_verified", true));
        assertThat(SocialOAuthSuccessHandler.profile("google", google).verified()).isTrue();
        OAuth2User naver = mock(OAuth2User.class);
        when(naver.getAttributes()).thenReturn(Map.of("response", Map.of("id", "n1", "email", "existing@example.com")));
        assertThat(SocialOAuthSuccessHandler.profile("naver", naver).verified()).isFalse();
    }
}
