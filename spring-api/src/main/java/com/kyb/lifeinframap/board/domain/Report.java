package com.kyb.lifeinframap.board.domain;

import com.kyb.lifeinframap.board.domain.*;
import com.kyb.lifeinframap.board.repository.*;
import com.kyb.lifeinframap.board.service.*;
import com.kyb.lifeinframap.board.dto.*;

import com.kyb.lifeinframap.account.domain.User;
import jakarta.persistence.*;
import java.time.OffsetDateTime;

/** Django `boards_report` 매핑. 게시글 또는 댓글 하나를 가리킵니다. */
@Entity
@Table(name = "boards_report")
public class Report {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "reporter_id", nullable = false)
    private User reporter;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "post_id")
    private Post post;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "comment_id")
    private Comment comment;

    @Column(nullable = false, columnDefinition = "text")
    private String reason;

    @Column(nullable = false, length = 20)
    private String status;

    @Column(name = "admin_memo", nullable = false, columnDefinition = "text")
    private String adminMemo = "";

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "processed_by_id")
    private User processedBy;

    @Column(name = "processed_at")
    private OffsetDateTime processedAt;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    protected Report() {
    }

    public static Report create(User reporter, Post post, Comment comment, String reason) {
        Report report = new Report();
        report.reporter = reporter;
        report.post = post;
        report.comment = comment;
        report.reason = reason;
        report.status = "pending";
        report.adminMemo = "";
        report.createdAt = OffsetDateTime.now();
        return report;
    }

    public void process(User admin, String status, String adminMemo) {
        this.status = status;
        this.adminMemo = adminMemo == null ? "" : adminMemo;
        this.processedBy = admin;
        this.processedAt = OffsetDateTime.now();
    }

    public Long getId() { return id; }
    public User getReporter() { return reporter; }
    public Post getPost() { return post; }
    public Comment getComment() { return comment; }
    public String getReason() { return reason; }
    public String getStatus() { return status; }
    public String getAdminMemo() { return adminMemo; }
    public User getProcessedBy() { return processedBy; }
    public OffsetDateTime getProcessedAt() { return processedAt; }
    public OffsetDateTime getCreatedAt() { return createdAt; }
}
