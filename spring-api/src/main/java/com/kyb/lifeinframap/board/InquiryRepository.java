package com.kyb.lifeinframap.board;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface InquiryRepository extends JpaRepository<Inquiry, Long> {

    Page<Inquiry> findByAuthorIdOrderByCreatedAtDesc(Integer authorId, Pageable pageable);

    Page<Inquiry> findByStatus(String status, Pageable pageable);
}
