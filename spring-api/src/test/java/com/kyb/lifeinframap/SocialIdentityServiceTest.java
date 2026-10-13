package com.kyb.lifeinframap;

import static org.assertj.core.api.Assertions.assertThat;

import com.kyb.lifeinframap.account.domain.User;
import com.kyb.lifeinframap.auth.service.SocialIdentityService;
import com.kyb.lifeinframap.support.ApiTestBase;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

class SocialIdentityServiceTest extends ApiTestBase {
    @Autowired SocialIdentityService identities;

    @Test
    void verifiedEmailLinksTheExistingOrdinaryAccount() {
        User existing = createUser();
        User social = identities.findOrCreate("google", "subject-1", existing.getEmail().toUpperCase(), true);
        assertThat(social.getId()).isEqualTo(existing.getId());
        assertThat(identities.findOrCreate("google", "subject-1", "other@example.com", false).getId())
                .isEqualTo(existing.getId());
    }

    @Test
    void unverifiedEmailCannotLinkAnExistingAccount() {
        User existing = createUser();
        User social = identities.findOrCreate("naver", "subject-2", existing.getEmail(), false);
        assertThat(social.getId()).isNotEqualTo(existing.getId());
        assertThat(social.getEmail()).isBlank();
        assertThat(social.getPassword()).startsWith("!");
    }
}
