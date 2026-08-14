package com.kyb.lifeinframap.board.repository;

import com.kyb.lifeinframap.board.domain.*;
import com.kyb.lifeinframap.board.repository.*;
import com.kyb.lifeinframap.board.service.*;
import com.kyb.lifeinframap.board.dto.*;

import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface InquiryRepository extends JpaRepository<Inquiry, Long> {

    Page<Inquiry> findByAuthorIdOrderByCreatedAtDesc(Integer authorId, Pageable pageable);

    List<Inquiry> findByAuthorIdOrderByCreatedAtDesc(Integer authorId);

    Page<Inquiry> findByStatus(String status, Pageable pageable);
}
