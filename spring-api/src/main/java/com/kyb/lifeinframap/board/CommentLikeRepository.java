package com.kyb.lifeinframap.board;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CommentLikeRepository extends JpaRepository<CommentLike, Long> {

    Optional<CommentLike> findByCommentIdAndUserId(Long commentId, Integer userId);

    long countByCommentId(Long commentId);
}
