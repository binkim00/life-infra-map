package com.kyb.lifeinframap.account;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface UserProfileRepository extends JpaRepository<UserProfile, Long> {

    boolean existsByNickname(String nickname);

    Optional<UserProfile> findByUserId(Integer userId);
}
