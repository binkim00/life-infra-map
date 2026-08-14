package com.kyb.lifeinframap.place.repository;

import com.kyb.lifeinframap.place.domain.*;
import com.kyb.lifeinframap.place.repository.*;
import com.kyb.lifeinframap.place.dto.*;

import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface UserSavedPlaceRepository extends JpaRepository<UserSavedPlace, Long> {

    Page<UserSavedPlace> findByUserId(Integer userId, Pageable pageable);

    List<UserSavedPlace> findByUserId(Integer userId);

    Optional<UserSavedPlace> findByUserIdAndPlaceKey(Integer userId, String placeKey);

    Optional<UserSavedPlace> findByIdAndUserId(Long id, Integer userId);
}
