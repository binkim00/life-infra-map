package com.kyb.lifeinframap.security;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.servlet.ServletException;
import java.io.IOException;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

class PublicWriteRateLimitFilterTest {

    @Test
    void trustedGatewaySeparatesClients() throws Exception {
        var filter = new PublicWriteRateLimitFilter(1, 1, "172.18.0.2");
        assertThat(status(filter, "172.18.0.2", "203.0.113.1")).isEqualTo(200);
        assertThat(status(filter, "172.18.0.2", "203.0.113.2")).isEqualTo(200);
        assertThat(status(filter, "172.18.0.2", "203.0.113.1")).isEqualTo(429);
    }

    @Test
    void untrustedDirectRequestCannotForgeClientAddress() throws Exception {
        var filter = new PublicWriteRateLimitFilter(1, 1, "172.18.0.2");
        assertThat(status(filter, "100.71.169.91", "203.0.113.1")).isEqualTo(200);
        assertThat(status(filter, "100.71.169.91", "203.0.113.2")).isEqualTo(429);
    }

    @Test
    void missingTrustConfigurationIgnoresForwardedHeader() throws Exception {
        var filter = new PublicWriteRateLimitFilter(1, 1, "");
        assertThat(status(filter, "172.18.0.2", "203.0.113.1")).isEqualTo(200);
        assertThat(status(filter, "172.18.0.2", "203.0.113.2")).isEqualTo(429);
    }

    private int status(PublicWriteRateLimitFilter filter, String remote, String forwarded)
            throws ServletException, IOException {
        var request = new MockHttpServletRequest("POST", "/api/auth/login");
        request.setRemoteAddr(remote);
        request.addHeader("X-Real-IP", forwarded);
        var response = new MockHttpServletResponse();
        filter.doFilter(request, response, new MockFilterChain());
        return response.getStatus();
    }
}
