package com.kyb.lifeinframap.board;

import com.kyb.lifeinframap.account.User;
import jakarta.persistence.*;
import java.time.OffsetDateTime;

/** Django `boards_post` 매핑. */
@Entity
@Table(name = "boards_post")
public class Post {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "board_type", nullable = false, length = 20)
    private String boardType;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(nullable = false, columnDefinition = "text")
    private String content;

    /** 저장소 키만 담습니다. 실제 파일은 S3 호환 저장소에 있습니다. */
    @Column(length = 100)
    private String image;

    @Column(name = "view_count", nullable = false)
    private int viewCount;

    @Column(name = "is_pinned", nullable = false)
    private boolean pinned;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "author_id", nullable = false)
    private User author;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    protected Post() {
    }

    public static Post create(User author, String boardType, String title, String content, String image) {
        Post post = new Post();
        post.author = author;
        post.boardType = boardType;
        post.title = title;
        post.content = content;
        post.image = image;
        post.viewCount = 0;
        post.pinned = false;
        OffsetDateTime now = OffsetDateTime.now();
        post.createdAt = now;
        post.updatedAt = now;
        return post;
    }

    public void edit(String title, String content, String image) {
        if (title != null) this.title = title;
        if (content != null) this.content = content;
        if (image != null) this.image = image;
        this.updatedAt = OffsetDateTime.now();
    }

    public void increaseViewCount() {
        this.viewCount += 1;
    }

    /** 공지는 목록 위에 고정합니다. Django 는 board_type 이 notice 면 항상 고정합니다. */
    public void pin(boolean pinned) {
        this.pinned = pinned;
    }

    public Long getId() { return id; }
    public String getBoardType() { return boardType; }
    public String getTitle() { return title; }
    public String getContent() { return content; }
    public String getImage() { return image; }
    public int getViewCount() { return viewCount; }
    public boolean isPinned() { return pinned; }
    public User getAuthor() { return author; }
    public OffsetDateTime getCreatedAt() { return createdAt; }
    public OffsetDateTime getUpdatedAt() { return updatedAt; }
}
