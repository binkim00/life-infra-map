package com.kyb.lifeinframap.board;

import java.time.OffsetDateTime;
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface NotificationRepository extends JpaRepository<Notification, Long> {

    Page<Notification> findByRecipientIdOrderByCreatedAtDesc(Integer recipientId, Pageable pageable);

    long countByRecipientIdAndReadFalse(Integer recipientId);

    List<Notification> findByRecipientIdOrderByCreatedAtDesc(Integer recipientId);

    @Modifying
    @Query("update Notification n set n.read = true where n.recipient.id = :userId and n.read = false")
    int markAllRead(@Param("userId") Integer userId);

    /** Django 는 목록을 볼 때 3일 지난 알림을 지웁니다. 같은 규칙을 씁니다. */
    @Modifying
    @Query("delete from Notification n where n.recipient.id = :userId and n.createdAt < :threshold")
    int deleteOlderThan(@Param("userId") Integer userId, @Param("threshold") OffsetDateTime threshold);
}
