package com.kyb.lifeinframap.place.repository;

import com.kyb.lifeinframap.place.domain.UserSavedPlaceGroup;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface UserSavedPlaceGroupRepository extends JpaRepository<UserSavedPlaceGroup, Long> {
    List<UserSavedPlaceGroup> findByUserIdOrderByUpdatedAtDescIdDesc(Integer userId);
    Optional<UserSavedPlaceGroup> findByIdAndUserId(Long id, Integer userId);
    Optional<UserSavedPlaceGroup> findByUserIdAndNameIgnoreCase(Integer userId, String name);
}
