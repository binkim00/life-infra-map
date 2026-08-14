package com.kyb.lifeinframap.board.domain;

import com.kyb.lifeinframap.board.domain.*;
import com.kyb.lifeinframap.board.repository.*;
import com.kyb.lifeinframap.board.service.*;
import com.kyb.lifeinframap.board.dto.*;

import com.kyb.lifeinframap.account.domain.User;
import jakarta.persistence.*;
import java.time.OffsetDateTime;

/** Django `boards_notification` 매핑. */
@Entity
@Table(name = "boards_notification")
public class Notification {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "recipient_id", nullable = false)
    private User recipient;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "sender_id")
    private User sender;

    @Column(name = "notification_type", nullable = false, length = 30)
    private String notificationType;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(nullable = false, columnDefinition = "text")
    private String message;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "target_post_id")
    private Post targetPost;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "target_comment_id")
    private Comment targetComment;

    @Column(name = "is_read", nullable = false)
    private boolean read;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    protected Notification() {
    }

    public static Notification create(User recipient, User sender, String type, String title,
                                      String message, Post targetPost, Comment targetComment) {
        Notification notification = new Notification();
        notification.recipient = recipient;
        notification.sender = sender;
        notification.notificationType = type;
        notification.title = title;
        notification.message = message;
        notification.targetPost = targetPost;
        notification.targetComment = targetComment;
        notification.read = false;
        notification.createdAt = OffsetDateTime.now();
        return notification;
    }

    public void markRead() {
        this.read = true;
    }

    public Long getId() { return id; }
    public User getRecipient() { return recipient; }
    public User getSender() { return sender; }
    public String getNotificationType() { return notificationType; }
    public String getTitle() { return title; }
    public String getMessage() { return message; }
    public Post getTargetPost() { return targetPost; }
    public Comment getTargetComment() { return targetComment; }
    public boolean isRead() { return read; }
    public OffsetDateTime getCreatedAt() { return createdAt; }
}
