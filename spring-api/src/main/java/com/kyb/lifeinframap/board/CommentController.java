package com.kyb.lifeinframap.board;

import com.kyb.lifeinframap.account.User;
import com.kyb.lifeinframap.account.UserRepository;
import jakarta.validation.constraints.NotBlank;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

/**
 * 댓글 API 입니다.
 *
 * 댓글이 달리면 글쓴이에게 알림을 보냅니다. 자기 글에 자기가 달면 보내지 않습니다.
 * Django `comment_create` 와 같은 규칙입니다.
 */
@RestController
@RequestMapping("/api/boards")
public class CommentController {

    private final CommentRepository commentRepository;
    private final PostRepository postRepository;
    private final NotificationRepository notificationRepository;
    private final UserRepository userRepository;
    private final BoardResponseAssembler assembler;
    private final PenaltyService penaltyService;

    public CommentController(
            CommentRepository commentRepository,
            PostRepository postRepository,
            NotificationRepository notificationRepository,
            UserRepository userRepository,
            BoardResponseAssembler assembler,
            PenaltyService penaltyService) {
        this.commentRepository = commentRepository;
        this.postRepository = postRepository;
        this.notificationRepository = notificationRepository;
        this.userRepository = userRepository;
        this.assembler = assembler;
        this.penaltyService = penaltyService;
    }

    public record CommentRequest(@NotBlank String content, Long parent) {
    }

    @PostMapping("/posts/{postId}/comments")
    @Transactional
    public ResponseEntity<?> create(@PathVariable Long postId, @RequestBody CommentRequest request,
                                    Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        UserPenalty penalty = penaltyService.findCurrent(user.getId());
        if (penalty != null) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN).body(penaltyService.blockedBody(penalty));
        }
        Post post = postRepository.findById(postId).orElse(null);
        if (post == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("detail", "게시글을 찾을 수 없습니다."));
        }

        Comment parent = null;
        if (request.parent() != null) {
            parent = commentRepository.findById(request.parent()).orElse(null);
            if (parent == null || !parent.getPost().getId().equals(postId)) {
                return ResponseEntity.badRequest().body(Map.of("detail", "답글을 달 댓글을 찾을 수 없습니다."));
            }
        }

        Comment comment = commentRepository.save(Comment.create(post, user, request.content(), parent));
        notifyIfNeeded(post, parent, user, comment);

        BoardResponseAssembler.AuthorContext context = assembler.loadAuthors(List.of(user));
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(assembler.comment(comment, context, user.getId(), List.of()));
    }

    @PatchMapping("/comments/{commentId}")
    @Transactional
    public ResponseEntity<?> update(@PathVariable Long commentId, @RequestBody CommentRequest request,
                                    Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        Comment comment = commentRepository.findById(commentId).orElse(null);
        if (comment == null) {
            return notFound();
        }
        if (!comment.getAuthor().getId().equals(user.getId())) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN)
                    .body(Map.of("detail", "본인이 작성한 댓글만 수정할 수 있습니다."));
        }
        comment.edit(request.content());

        BoardResponseAssembler.AuthorContext context = assembler.loadAuthors(List.of(comment.getAuthor()));
        return ResponseEntity.ok(assembler.comment(comment, context, user.getId(), List.of()));
    }

    @DeleteMapping("/comments/{commentId}")
    @Transactional
    public ResponseEntity<?> delete(@PathVariable Long commentId, Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        Comment comment = commentRepository.findById(commentId).orElse(null);
        if (comment == null) {
            return notFound();
        }
        if (!comment.getAuthor().getId().equals(user.getId()) && !user.isStaff()) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN)
                    .body(Map.of("detail", "본인이 작성한 댓글만 삭제할 수 있습니다."));
        }
        commentRepository.delete(comment);
        return ResponseEntity.noContent().build();
    }

    /** 답글이면 원댓글 작성자에게, 아니면 글쓴이에게 알립니다. 본인에게는 보내지 않습니다. */
    private void notifyIfNeeded(Post post, Comment parent, User actor, Comment comment) {
        User recipient = parent != null ? parent.getAuthor() : post.getAuthor();
        if (recipient == null || recipient.getId().equals(actor.getId())) {
            return;
        }
        String type = parent != null ? "reply" : "comment";
        String title = parent != null ? "새 답글이 달렸어요." : "새 댓글이 달렸어요.";
        notificationRepository.save(Notification.create(
                recipient, actor, type, title, comment.getContent(), post, comment));
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

    private ResponseEntity<Map<String, Object>> notFound() {
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("detail", "댓글을 찾을 수 없습니다."));
    }
}
