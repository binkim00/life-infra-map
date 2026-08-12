package com.kyb.lifeinframap.board;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/**
 * boards 도메인 리포지토리 모음입니다.
 *
 * 인터페이스가 짧아 파일을 나누지 않고 한곳에 둡니다.
 */
public final class BoardRepositories {

    private BoardRepositories() {
    }

    public interface PostRepository extends JpaRepository<Post, Long> {
        Page<Post> findByBoardType(String boardType, Pageable pageable);

        Page<Post> findByBoardTypeAndTitleContainingIgnoreCase(String boardType, String title, Pageable pageable);

        long countByAuthorId(Integer authorId);
    }

    public interface CommentRepository extends JpaRepository<Comment, Long> {
        List<Comment> findByPostIdOrderByCreatedAtAsc(Long postId);

        long countByPostId(Long postId);

        long countByAuthorId(Integer authorId);
    }

    public interface PostLikeRepository extends JpaRepository<PostLike, Long> {
        Optional<PostLike> findByPostIdAndUserId(Long postId, Integer userId);

        long countByPostId(Long postId);
    }

    public interface CommentLikeRepository extends JpaRepository<CommentLike, Long> {
        Optional<CommentLike> findByCommentIdAndUserId(Long commentId, Integer userId);

        long countByCommentId(Long commentId);
    }

    public interface CommentDislikeRepository extends JpaRepository<CommentDislike, Long> {
        Optional<CommentDislike> findByCommentIdAndUserId(Long commentId, Integer userId);

        long countByCommentId(Long commentId);
    }

    public interface ReportRepository extends JpaRepository<Report, Long> {
        Page<Report> findByStatus(String status, Pageable pageable);

        boolean existsByReporterIdAndPostId(Integer reporterId, Long postId);

        boolean existsByReporterIdAndCommentId(Integer reporterId, Long commentId);
    }

    public interface NotificationRepository extends JpaRepository<Notification, Long> {
        Page<Notification> findByRecipientIdOrderByCreatedAtDesc(Integer recipientId, Pageable pageable);

        long countByRecipientIdAndReadFalse(Integer recipientId);

        @Query("update Notification n set n.read = true where n.recipient.id = :userId and n.read = false")
        @org.springframework.data.jpa.repository.Modifying
        int markAllRead(@Param("userId") Integer userId);
    }

    public interface InquiryRepository extends JpaRepository<Inquiry, Long> {
        Page<Inquiry> findByAuthorIdOrderByCreatedAtDesc(Integer authorId, Pageable pageable);

        Page<Inquiry> findByStatus(String status, Pageable pageable);
    }

    public interface UserPenaltyRepository extends JpaRepository<UserPenalty, Long> {
        List<UserPenalty> findByUserIdOrderByCreatedAtDesc(Integer userId);

        /** 아직 유효한 제재만 찾습니다. 기간이 없는 건 영구 제재입니다. */
        @Query("""
                select p from UserPenalty p
                where p.user.id = :userId and p.active = true
                  and (p.endAt is null or p.endAt > :now)
                order by p.createdAt desc
                """)
        List<UserPenalty> findEffective(@Param("userId") Integer userId, @Param("now") OffsetDateTime now);
    }
}
