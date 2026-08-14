package com.kyb.lifeinframap.board.domain;

import com.kyb.lifeinframap.board.domain.*;
import com.kyb.lifeinframap.board.repository.*;
import com.kyb.lifeinframap.board.service.*;
import com.kyb.lifeinframap.board.dto.*;

import com.kyb.lifeinframap.account.domain.User;
import jakarta.persistence.*;
import java.time.OffsetDateTime;

/** Django `boards_inquiry` 매핑. 사용자 문의와 관리자 답변입니다. */
@Entity
@Table(name = "boards_inquiry")
public class Inquiry {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "author_id", nullable = false)
    private User author;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(nullable = false, columnDefinition = "text")
    private String content;

    @Column(nullable = false, length = 20)
    private String status;

    @Column(name = "admin_reply", nullable = false, columnDefinition = "text")
    private String adminReply = "";

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "replied_by_id")
    private User repliedBy;

    @Column(name = "replied_at")
    private OffsetDateTime repliedAt;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    protected Inquiry() {
    }

    public static Inquiry create(User author, String title, String content) {
        Inquiry inquiry = new Inquiry();
        inquiry.author = author;
        inquiry.title = title;
        inquiry.content = content;
        inquiry.status = "pending";
        inquiry.adminReply = "";
        OffsetDateTime now = OffsetDateTime.now();
        inquiry.createdAt = now;
        inquiry.updatedAt = now;
        return inquiry;
    }

    public void reply(User admin, String status, String adminReply) {
        this.status = status;
        if (adminReply != null) {
            this.adminReply = adminReply;
            this.repliedBy = admin;
            this.repliedAt = OffsetDateTime.now();
        }
        this.updatedAt = OffsetDateTime.now();
    }

    public Long getId() { return id; }
    public User getAuthor() { return author; }
    public String getTitle() { return title; }
    public String getContent() { return content; }
    public String getStatus() { return status; }
    public String getAdminReply() { return adminReply; }
    public User getRepliedBy() { return repliedBy; }
    public OffsetDateTime getRepliedAt() { return repliedAt; }
    public OffsetDateTime getCreatedAt() { return createdAt; }
    public OffsetDateTime getUpdatedAt() { return updatedAt; }
}
