package com.kyb.lifeinframap.board.repository;

import com.kyb.lifeinframap.board.domain.*;
import com.kyb.lifeinframap.board.repository.*;
import com.kyb.lifeinframap.board.service.*;
import com.kyb.lifeinframap.board.dto.*;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CommentDislikeRepository extends JpaRepository<CommentDislike, Long> {

    Optional<CommentDislike> findByCommentIdAndUserId(Long commentId, Integer userId);

    long countByCommentId(Long commentId);
}
