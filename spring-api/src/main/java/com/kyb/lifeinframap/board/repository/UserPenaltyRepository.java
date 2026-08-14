package com.kyb.lifeinframap.board.repository;

import com.kyb.lifeinframap.board.domain.*;
import com.kyb.lifeinframap.board.repository.*;
import com.kyb.lifeinframap.board.service.*;
import com.kyb.lifeinframap.board.dto.*;

import java.time.OffsetDateTime;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface UserPenaltyRepository extends JpaRepository<UserPenalty, Long> {

    List<UserPenalty> findByUserIdOrderByCreatedAtDesc(Integer userId);

    /** 아직 유효한 제재만 찾습니다. 기간이 없으면 영구 제재입니다. */
    @Query("""
            select p from UserPenalty p
            where p.user.id = :userId and p.active = true
              and (p.endAt is null or p.endAt > :now)
            order by p.createdAt desc
            """)
    List<UserPenalty> findEffective(@Param("userId") Integer userId, @Param("now") OffsetDateTime now);
}
