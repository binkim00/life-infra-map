package com.kyb.lifeinframap.auth.service;

import com.kyb.lifeinframap.account.domain.User;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import java.io.IOException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.stereotype.Component;

@Component
public class SocialOAuthSuccessHandler implements AuthenticationSuccessHandler {
    private final SocialIdentityService identities;
    private final SocialLoginTicketService tickets;
    private final SocialOAuthSettings settings;

    public SocialOAuthSuccessHandler(SocialIdentityService identities, SocialLoginTicketService tickets,
            SocialOAuthSettings settings) {
        this.identities = identities;
        this.tickets = tickets;
        this.settings = settings;
    }

    @Override
    public void onAuthenticationSuccess(HttpServletRequest request, HttpServletResponse response,
            Authentication authentication) throws IOException {
        HttpSession session = request.getSession(false);
        if (session == null || !(authentication instanceof OAuth2AuthenticationToken oauth)) {
            response.sendError(400, "Social login session expired");
            return;
        }
        String client = (String) session.getAttribute("social_client");
        String nonce = (String) session.getAttribute("social_nonce");
        String provider = oauth.getAuthorizedClientRegistrationId();
        if ((!"web".equals(client) && !"mobile".equals(client)) || nonce == null
                || !settings.available(provider)) {
            session.invalidate();
            response.sendError(400, "Invalid social login session");
            return;
        }
        try {
            Profile profile = profile(provider, oauth.getPrincipal());
            User user = identities.findOrCreate(provider, profile.subject(), profile.email(), profile.verified());
            String ticket = tickets.issue(user);
            session.invalidate();
            String destination = "mobile".equals(client) ? "lifeinframap://oauth/callback"
                    : settings.publicBaseUrl() + "/oauth/callback";
            response.sendRedirect(destination + "?ticket=" + encode(ticket) + "&nonce=" + encode(nonce));
        } catch (IllegalArgumentException | IllegalStateException exception) {
            session.invalidate();
            response.sendError(400, "Social account could not be verified");
        }
    }

    public static Profile profile(String provider, OAuth2User principal) {
        Map<String, Object> attributes = principal.getAttributes();
        if ("google".equals(provider)) {
            return new Profile(string(attributes.get("sub")), string(attributes.get("email")),
                    Boolean.TRUE.equals(attributes.get("email_verified")));
        }
        if ("kakao".equals(provider)) {
            Map<?, ?> account = attributes.get("kakao_account") instanceof Map<?, ?> value ? value : Map.of();
            return new Profile(string(attributes.get("id")), string(account.get("email")),
                    Boolean.TRUE.equals(account.get("is_email_verified"))
                            && Boolean.TRUE.equals(account.get("is_email_valid")));
        }
        if ("naver".equals(provider)) {
            Map<?, ?> data = attributes.get("response") instanceof Map<?, ?> value ? value : Map.of();
            return new Profile(string(data.get("id")), string(data.get("email")), false);
        }
        throw new IllegalArgumentException("Unsupported provider");
    }

    private static String string(Object value) { return value == null ? "" : value.toString(); }
    private static String encode(String value) { return URLEncoder.encode(value, StandardCharsets.UTF_8); }
    public record Profile(String subject, String email, boolean verified) {}
}
