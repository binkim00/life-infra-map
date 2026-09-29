package com.kyb.lifeinframap.auth.service;

import com.kyb.lifeinframap.account.domain.User;
import com.kyb.lifeinframap.account.domain.UserProfile;
import com.kyb.lifeinframap.account.repository.UserProfileRepository;
import com.kyb.lifeinframap.account.repository.UserRepository;
import com.kyb.lifeinframap.auth.domain.SocialIdentity;
import com.kyb.lifeinframap.auth.repository.SocialIdentityRepository;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.OffsetDateTime;
import java.util.Base64;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SocialIdentityService {
    private final SocialIdentityRepository identities;
    private final UserRepository users;
    private final UserProfileRepository profiles;
    private final SecureRandom random = new SecureRandom();

    public SocialIdentityService(SocialIdentityRepository identities, UserRepository users,
            UserProfileRepository profiles) {
        this.identities = identities;
        this.users = users;
        this.profiles = profiles;
    }

    @Transactional
    public User findOrCreate(String provider, String subject, String email, boolean emailVerified) {
        if (!List.of("naver", "google", "kakao").contains(provider)
                || subject == null || subject.isBlank() || subject.length() > 255) {
            throw new IllegalArgumentException("Invalid social identity");
        }
        SocialIdentity linked = identities.findByProviderAndProviderSubject(provider, subject).orElse(null);
        if (linked != null) {
            User user = linked.getUser();
            if (!user.isActive()) throw new IllegalStateException("Inactive account");
            user.markLoggedIn(OffsetDateTime.now());
            return user;
        }

        String verifiedEmail = emailVerified && email != null ? email.trim().toLowerCase(Locale.ROOT) : "";
        if (verifiedEmail.length() > 254 || !verifiedEmail.matches("[^@\\s]+@[^@\\s]+\\.[^@\\s]+")) {
            verifiedEmail = "";
        }
        User user = null;
        if (!verifiedEmail.isBlank()) {
            List<User> matches = users.findByEmailIgnoreCase(verifiedEmail);
            if (matches.size() == 1 && matches.get(0).isActive()
                    && !matches.get(0).isStaff() && !matches.get(0).isSuperuser()) {
                user = matches.get(0);
            }
        }
        if (user == null) {
            String username = "social_" + provider + "_" + sha256(subject).substring(0, 24);
            byte[] bytes = new byte[24];
            random.nextBytes(bytes);
            // Django's unusable-password prefix prevents password login.
            user = users.save(User.create(username, verifiedEmail, "!" + Base64.getUrlEncoder()
                    .withoutPadding().encodeToString(bytes)));
            String nickname = "소셜사용자" + user.getId();
            while (profiles.existsByNickname(nickname)) nickname += "_";
            profiles.save(new UserProfile(user, nickname));
        }
        identities.save(new SocialIdentity(user, provider, subject));
        user.markLoggedIn(OffsetDateTime.now());
        return user;
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 unavailable", exception);
        }
    }
}
