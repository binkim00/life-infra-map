package com.kyb.lifeinframap.board;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CommentRepository extends JpaRepository<Comment, Long> {

    List<Comment> findByPostIdOrderByCreatedAtAsc(Long postId);

    long countByPostId(Long postId);

    long countByAuthorId(Integer authorId);

    List<Comment> findByAuthorIdOrderByCreatedAtDesc(Integer authorId);
}
