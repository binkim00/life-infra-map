package com.kyb.lifeinframap.place.repository;

import com.kyb.lifeinframap.place.domain.*;
import com.kyb.lifeinframap.place.repository.*;
import com.kyb.lifeinframap.place.dto.*;

import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface UserSavedPlaceRepository extends JpaRepository<UserSavedPlace, Long> {

    Page<UserSavedPlace> findByUserId(Integer userId, Pageable pageable);

    List<UserSavedPlace> findByUserId(Integer userId);

    Optional<UserSavedPlace> findByUserIdAndPlaceKey(Integer userId, String placeKey);

    Optional<UserSavedPlace> findByIdAndUserId(Long id, Integer userId);

    @Query("""
            select saved from UserSavedPlace saved
            where saved.user.id = :userId
              and (:source is null or :source = '' or saved.source = :source)
              and (:keyword is null or :keyword = ''
                   or lower(saved.name) like lower(concat('%', :keyword, '%'))
                   or lower(saved.category) like lower(concat('%', :keyword, '%'))
                   or lower(saved.address) like lower(concat('%', :keyword, '%'))
                   or lower(saved.memo) like lower(concat('%', :keyword, '%')))
            """)
    Page<UserSavedPlace> search(
            @Param("userId") Integer userId,
            @Param("keyword") String keyword,
            @Param("source") String source,
            Pageable pageable);
}
