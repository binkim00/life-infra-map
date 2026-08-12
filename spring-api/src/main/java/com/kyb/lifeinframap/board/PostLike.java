package com.kyb.lifeinframap.board;

import com.kyb.lifeinframap.account.User;
import jakarta.persistence.*;
import java.time.OffsetDateTime;

/** Django `boards_postlike` 매핑. (`post_id`, `user_id`) 조합이 유일합니다. */
@Entity
@Table(name = "boards_postlike", uniqueConstraints = @UniqueConstraint(name = "unique_post_like", columnNames = {"post_id", "user_id"}))
public class PostLike {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "post_id", nullable = false)
    private Post post;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    protected PostLike() {
    }

    public PostLike(Post post, User user) {
        this.post = post;
        this.user = user;
        this.createdAt = OffsetDateTime.now();
    }

    public Long getId() { return id; }
    public Post getPost() { return post; }
    public User getUser() { return user; }
}
