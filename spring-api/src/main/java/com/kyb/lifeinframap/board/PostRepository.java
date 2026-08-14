package com.kyb.lifeinframap.board;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PostRepository extends JpaRepository<Post, Long> {

    long countByAuthorId(Integer authorId);

    List<Post> findByAuthorIdOrderByCreatedAtDesc(Integer authorId);
}
