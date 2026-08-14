package com.kyb.lifeinframap.board;

import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PostLikeRepository extends JpaRepository<PostLike, Long> {

    Optional<PostLike> findByPostIdAndUserId(Long postId, Integer userId);

    List<PostLike> findByUserIdOrderByCreatedAtDesc(Integer userId);

    long countByPostId(Long postId);
}
