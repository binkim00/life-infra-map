package com.kyb.lifeinframap.board.repository;

import com.kyb.lifeinframap.board.domain.*;
import com.kyb.lifeinframap.board.repository.*;
import com.kyb.lifeinframap.board.service.*;
import com.kyb.lifeinframap.board.dto.*;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ReportRepository extends JpaRepository<Report, Long> {

    Page<Report> findByStatus(String status, Pageable pageable);

    boolean existsByReporterIdAndPostId(Integer reporterId, Long postId);

    boolean existsByReporterIdAndCommentId(Integer reporterId, Long commentId);

    long countByPostAuthorId(Integer authorId);

    long countByCommentAuthorId(Integer authorId);
}
