package com.kyb.lifeinframap.auth.repository;

import com.kyb.lifeinframap.auth.domain.SocialLoginTicket;
import jakarta.persistence.LockModeType;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface SocialLoginTicketRepository extends JpaRepository<SocialLoginTicket, Long> {
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select t from SocialLoginTicket t where t.ticketHash = :hash")
    Optional<SocialLoginTicket> lockByTicketHash(@Param("hash") String hash);
}
