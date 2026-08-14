package com.kyb.lifeinframap.board.domain;

import com.kyb.lifeinframap.board.domain.*;
import com.kyb.lifeinframap.board.repository.*;
import com.kyb.lifeinframap.board.service.*;
import com.kyb.lifeinframap.board.dto.*;

import com.kyb.lifeinframap.account.domain.User;
import jakarta.persistence.*;
import java.time.OffsetDateTime;

/** Django `boards_comment` 매핑. `parent` 가 있으면 대댓글입니다. */
@Entity
@Table(name = "boards_comment")
public class Comment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, columnDefinition = "text")
    private String content;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "post_id", nullable = false)
    private Post post;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "author_id", nullable = false)
    private User author;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "parent_id")
    private Comment parent;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    protected Comment() {
    }

    public static Comment create(Post post, User author, String content, Comment parent) {
        Comment comment = new Comment();
        comment.post = post;
        comment.author = author;
        comment.content = content;
        comment.parent = parent;
        OffsetDateTime now = OffsetDateTime.now();
        comment.createdAt = now;
        comment.updatedAt = now;
        return comment;
    }

    public void edit(String content) {
        this.content = content;
        this.updatedAt = OffsetDateTime.now();
    }

    public Long getId() { return id; }
    public String getContent() { return content; }
    public Post getPost() { return post; }
    public User getAuthor() { return author; }
    public Comment getParent() { return parent; }
    public OffsetDateTime getCreatedAt() { return createdAt; }
    public OffsetDateTime getUpdatedAt() { return updatedAt; }
}
