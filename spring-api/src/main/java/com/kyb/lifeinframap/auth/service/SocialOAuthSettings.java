package com.kyb.lifeinframap.auth.service;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.stereotype.Component;

@Component
public class SocialOAuthSettings {
    private final String publicBaseUrl;
    private final Map<String, ClientRegistration> registrations;

    public SocialOAuthSettings(
            @Value("${app.social.enabled:false}") boolean enabled,
            @Value("${app.social.public-base-url:}") String publicBaseUrl,
            @Value("${app.social.google-client-id:}") String googleId,
            @Value("${app.social.google-client-secret:}") String googleSecret,
            @Value("${app.social.naver-client-id:}") String naverId,
            @Value("${app.social.naver-client-secret:}") String naverSecret,
            @Value("${app.social.kakao-client-id:}") String kakaoId,
            @Value("${app.social.kakao-client-secret:}") String kakaoSecret) {
        this.publicBaseUrl = publicBaseUrl.replaceAll("/+$", "");
        Map<String, ClientRegistration> configured = new LinkedHashMap<>();
        if (enabled) {
            if (!this.publicBaseUrl.startsWith("https://"))
                throw new IllegalStateException("Social login requires an HTTPS public base URL");
            String redirect = this.publicBaseUrl + "/spring/api/login/oauth2/code/{registrationId}";
            if (present(googleId, googleSecret)) {
                configured.put("google", ClientRegistration.withRegistrationId("google")
                        .clientId(googleId).clientSecret(googleSecret)
                        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                        .redirectUri(redirect).scope("openid", "email", "profile")
                        .authorizationUri("https://accounts.google.com/o/oauth2/v2/auth")
                        .tokenUri("https://oauth2.googleapis.com/token")
                        .jwkSetUri("https://www.googleapis.com/oauth2/v3/certs")
                        .issuerUri("https://accounts.google.com")
                        .userInfoUri("https://openidconnect.googleapis.com/v1/userinfo")
                        .userNameAttributeName("sub").clientName("Google").build());
            }
            if (present(naverId, naverSecret)) {
                configured.put("naver", ClientRegistration.withRegistrationId("naver")
                        .clientId(naverId).clientSecret(naverSecret)
                        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_POST)
                        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                        .redirectUri(redirect).scope("email")
                        .authorizationUri("https://nid.naver.com/oauth2.0/authorize")
                        .tokenUri("https://nid.naver.com/oauth2.0/token")
                        .userInfoUri("https://openapi.naver.com/v1/nid/me")
                        .userNameAttributeName("response").clientName("Naver").build());
            }
            if (present(kakaoId, kakaoSecret)) {
                configured.put("kakao", ClientRegistration.withRegistrationId("kakao")
                        .clientId(kakaoId).clientSecret(kakaoSecret)
                        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_POST)
                        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                        .redirectUri(redirect).scope("account_email")
                        .authorizationUri("https://kauth.kakao.com/oauth/authorize")
                        .tokenUri("https://kauth.kakao.com/oauth/token")
                        .userInfoUri("https://kapi.kakao.com/v2/user/me")
                        .userNameAttributeName("id").clientName("Kakao").build());
            }
        }
        this.registrations = Map.copyOf(configured);
    }

    private static boolean present(String id, String secret) {
        return id != null && !id.isBlank() && secret != null && !secret.isBlank();
    }

    public boolean available(String provider) { return registrations.containsKey(provider); }
    public java.util.Set<String> providers() { return registrations.keySet(); }
    public String publicBaseUrl() { return publicBaseUrl; }
    public ClientRegistrationRepository repository() {
        return registrations.isEmpty() ? null : new InMemoryClientRegistrationRepository(registrations);
    }
}
