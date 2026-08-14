package com.kyb.lifeinframap.board.controller;

import com.kyb.lifeinframap.board.domain.*;
import com.kyb.lifeinframap.board.repository.*;
import com.kyb.lifeinframap.board.service.*;
import com.kyb.lifeinframap.board.dto.*;

import com.kyb.lifeinframap.account.domain.User;
import com.kyb.lifeinframap.account.repository.UserRepository;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

/**
 * 좋아요/싫어요 토글입니다.
 *
 * 이미 눌러 두었으면 취소합니다. 댓글은 좋아요와 싫어요가 동시에 켜지지 않습니다.
 */
@RestController
@RequestMapping("/api/boards")
public class ReactionController {

    private final PostRepository postRepository;
    private final CommentRepository commentRepository;
    private final PostLikeRepository postLikeRepository;
    private final CommentLikeRepository commentLikeRepository;
    private final CommentDislikeRepository commentDislikeRepository;
    private final UserRepository userRepository;
    private final PenaltyService penaltyService;

    public ReactionController(
            PostRepository postRepository,
            CommentRepository commentRepository,
            PostLikeRepository postLikeRepository,
            CommentLikeRepository commentLikeRepository,
            CommentDislikeRepository commentDislikeRepository,
            UserRepository userRepository,
            PenaltyService penaltyService) {
        this.postRepository = postRepository;
        this.commentRepository = commentRepository;
        this.postLikeRepository = postLikeRepository;
        this.commentLikeRepository = commentLikeRepository;
        this.commentDislikeRepository = commentDislikeRepository;
        this.userRepository = userRepository;
        this.penaltyService = penaltyService;
    }

    @PostMapping("/posts/{postId}/like")
    @Transactional
    public ResponseEntity<?> togglePostLike(@PathVariable Long postId, Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        ResponseEntity<?> blocked = blockedOrNull(user);
        if (blocked != null) {
            return blocked;
        }
        Post post = postRepository.findById(postId).orElse(null);
        if (post == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("detail", "게시글을 찾을 수 없습니다."));
        }

        boolean liked;
        var existing = postLikeRepository.findByPostIdAndUserId(postId, user.getId());
        if (existing.isPresent()) {
            postLikeRepository.delete(existing.get());
            liked = false;
        } else {
            postLikeRepository.save(new PostLike(post, user));
            liked = true;
        }

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("is_liked", liked);
        body.put("likes_count", postLikeRepository.countByPostId(postId));
        return ResponseEntity.ok(body);
    }

    @PostMapping("/comments/{commentId}/like")
    @Transactional
    public ResponseEntity<?> toggleCommentLike(@PathVariable Long commentId, Authentication authentication) {
        return toggleCommentReaction(commentId, authentication, true);
    }

    @PostMapping("/comments/{commentId}/dislike")
    @Transactional
    public ResponseEntity<?> toggleCommentDislike(@PathVariable Long commentId, Authentication authentication) {
        return toggleCommentReaction(commentId, authentication, false);
    }

    private ResponseEntity<?> toggleCommentReaction(Long commentId, Authentication authentication, boolean like) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        ResponseEntity<?> blocked = blockedOrNull(user);
        if (blocked != null) {
            return blocked;
        }
        Comment comment = commentRepository.findById(commentId).orElse(null);
        if (comment == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("detail", "댓글을 찾을 수 없습니다."));
        }

        var likeRow = commentLikeRepository.findByCommentIdAndUserId(commentId, user.getId());
        var dislikeRow = commentDislikeRepository.findByCommentIdAndUserId(commentId, user.getId());

        if (like) {
            if (likeRow.isPresent()) {
                commentLikeRepository.delete(likeRow.get());
            } else {
                // 좋아요를 누르면 싫어요는 해제합니다.
                dislikeRow.ifPresent(commentDislikeRepository::delete);
                commentLikeRepository.save(new CommentLike(comment, user));
            }
        } else {
            if (dislikeRow.isPresent()) {
                commentDislikeRepository.delete(dislikeRow.get());
            } else {
                likeRow.ifPresent(commentLikeRepository::delete);
                commentDislikeRepository.save(new CommentDislike(comment, user));
            }
        }

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("is_liked", commentLikeRepository.findByCommentIdAndUserId(commentId, user.getId()).isPresent());
        body.put("is_disliked", commentDislikeRepository.findByCommentIdAndUserId(commentId, user.getId()).isPresent());
        body.put("likes_count", commentLikeRepository.countByCommentId(commentId));
        body.put("dislikes_count", commentDislikeRepository.countByCommentId(commentId));
        return ResponseEntity.ok(body);
    }

    private ResponseEntity<?> blockedOrNull(User user) {
        UserPenalty penalty = penaltyService.findCurrent(user.getId());
        if (penalty == null) {
            return null;
        }
        return ResponseEntity.status(HttpStatus.FORBIDDEN).body(penaltyService.blockedBody(penalty));
    }

    private User currentUser(Authentication authentication) {
        if (authentication == null || authentication.getName() == null) {
            return null;
        }
        try {
            return userRepository.findById(Integer.valueOf(authentication.getName())).orElse(null);
        } catch (NumberFormatException exception) {
            return null;
        }
    }

    private ResponseEntity<Map<String, Object>> unauthorized() {
        return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(Map.of("detail", "로그인이 필요합니다."));
    }
}
