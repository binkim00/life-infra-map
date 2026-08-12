package com.kyb.lifeinframap.board;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CommentDislikeRepository extends JpaRepository<CommentDislike, Long> {

    Optional<CommentDislike> findByCommentIdAndUserId(Long commentId, Integer userId);

    long countByCommentId(Long commentId);
}
