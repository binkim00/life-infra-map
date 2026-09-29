package com.kyb.lifeinframap;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

import com.kyb.lifeinframap.account.domain.User;
import com.kyb.lifeinframap.support.ApiTestBase;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest(properties = {
        "app.social.enabled=true", "app.social.public-base-url=https://example.test",
        "app.social.google-client-id=test-client", "app.social.google-client-secret=test-secret",
        "app.social.naver-client-id=test-naver", "app.social.naver-client-secret=test-secret",
        "app.social.kakao-client-id=test-kakao", "app.social.kakao-client-secret=test-secret"
})
class SocialOAuthEnabledTest extends ApiTestBase {
    @Test
    void apiBearerOverridesOldOAuthSessionAndSessionAloneCannotAuthenticate() throws Exception {
        User oldUser = createUser();
        User currentUser = createUser();
        MockHttpSession session = new MockHttpSession();
        SecurityContext oldContext = SecurityContextHolder.createEmptyContext();
        oldContext.setAuthentication(new UsernamePasswordAuthenticationToken(
                String.valueOf(oldUser.getId()), null, List.of()));
        session.setAttribute(HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY, oldContext);

        mockMvc.perform(get("/api/accounts/me").session(session)
                        .header("Authorization", bearer(currentUser)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(currentUser.getId()));
        mockMvc.perform(get("/api/accounts/me").session(session))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void startStoresSessionAndUsesFixedExternalCallback() throws Exception {
        mockMvc.perform(get("/api/auth/social/providers"))
                .andExpect(status().isOk());
        String nonce = "123456789012345678901234";
        MvcResult start = mockMvc.perform(get("/api/auth/social/google/start")
                        .param("client", "web").param("nonce", nonce))
                .andExpect(status().isFound()).andReturn();
        assertThat(start.getResponse().getRedirectedUrl()).isEqualTo(
                "https://example.test/spring/api/oauth2/authorization/google");
        MockHttpSession session = (MockHttpSession) start.getRequest().getSession(false);
        assertThat(session.getAttribute("social_nonce")).isEqualTo(nonce);
        MvcResult authorization = mockMvc.perform(get("/api/oauth2/authorization/google").session(session))
                .andExpect(status().isFound()).andReturn();
        String redirect = authorization.getResponse().getRedirectedUrl();
        assertThat(redirect).startsWith("https://accounts.google.com/o/oauth2/v2/auth?");
        assertThat(redirect).contains("redirect_uri=https://example.test/spring/api/login/oauth2/code/google");
        assertThat(redirect).contains("state=");
    }
}
