package com.kyb.lifeinframap.auth.repository;

import com.kyb.lifeinframap.auth.domain.SocialIdentity;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface SocialIdentityRepository extends JpaRepository<SocialIdentity, Long> {
    Optional<SocialIdentity> findByProviderAndProviderSubject(String provider, String providerSubject);
}
