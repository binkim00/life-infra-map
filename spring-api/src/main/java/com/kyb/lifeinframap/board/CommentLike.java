package com.kyb.lifeinframap.board;

import com.kyb.lifeinframap.account.User;
import jakarta.persistence.*;
import java.time.OffsetDateTime;

/** Django `boards_commentlike` 매핑. (`comment_id`, `user_id`) 조합이 유일합니다. */
@Entity
@Table(name = "boards_commentlike", uniqueConstraints = @UniqueConstraint(name = "unique_comment_like", columnNames = {"comment_id", "user_id"}))
public class CommentLike {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "comment_id", nullable = false)
    private Comment comment;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    protected CommentLike() {
    }

    public CommentLike(Comment comment, User user) {
        this.comment = comment;
        this.user = user;
        this.createdAt = OffsetDateTime.now();
    }

    public Long getId() { return id; }
    public Comment getComment() { return comment; }
    public User getUser() { return user; }
}
