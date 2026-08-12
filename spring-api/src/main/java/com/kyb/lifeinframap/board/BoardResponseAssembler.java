package com.kyb.lifeinframap.board;

import com.kyb.lifeinframap.account.User;
import com.kyb.lifeinframap.account.UserProfile;
import com.kyb.lifeinframap.account.UserProfileRepository;
import com.kyb.lifeinframap.tier.ContributionService;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * 게시글/댓글 응답을 만듭니다.
 *
 * 필드 이름과 형태는 Django `boards/serializers.py` 와 같아야 합니다.
 * 프론트가 그대로 읽고 있어서 하나라도 다르면 화면이 비어 보입니다.
 *
 * 작성자 등급은 목록 전체를 한 번에 계산합니다. 한 명씩 조회하면 N+1 이 됩니다.
 */
@Component
public class BoardResponseAssembler {

    private final UserProfileRepository profileRepository;
    private final ContributionService contributionService;
    private final CommentRepository commentRepository;
    private final PostLikeRepository postLikeRepository;
    private final CommentLikeRepository commentLikeRepository;
    private final CommentDislikeRepository commentDislikeRepository;
    private final String mediaBaseUrl;

    public BoardResponseAssembler(
            UserProfileRepository profileRepository,
            ContributionService contributionService,
            CommentRepository commentRepository,
            PostLikeRepository postLikeRepository,
            CommentLikeRepository commentLikeRepository,
            CommentDislikeRepository commentDislikeRepository,
            @Value("${app.media.base-url:}") String mediaBaseUrl) {
        this.profileRepository = profileRepository;
        this.contributionService = contributionService;
        this.commentRepository = commentRepository;
        this.postLikeRepository = postLikeRepository;
        this.commentLikeRepository = commentLikeRepository;
        this.commentDislikeRepository = commentDislikeRepository;
        this.mediaBaseUrl = mediaBaseUrl == null ? "" : mediaBaseUrl.replaceAll("/+$", "");
    }

    /** 작성자 정보를 한 번에 모아 두는 캐시입니다. 목록 응답에서 재사용합니다. */
    public record AuthorContext(Map<Integer, String> nicknames,
                                Map<Integer, String> profileImages,
                                Map<Integer, ContributionService.TierInfo> tiers) {
    }

    public AuthorContext loadAuthors(List<User> authors) {
        List<Integer> ids = new ArrayList<>(new HashSet<>(authors.stream().map(User::getId).toList()));
        Map<Integer, String> nicknames = new HashMap<>();
        Map<Integer, String> images = new HashMap<>();
        for (Integer id : ids) {
            UserProfile profile = profileRepository.findByUserId(id).orElse(null);
            nicknames.put(id, profile != null ? profile.getNickname() : null);
            images.put(id, profile != null ? profile.getProfileImage() : null);
        }
        Set<Integer> staffIds = authors.stream().filter(User::isStaff).map(User::getId).collect(java.util.stream.Collectors.toSet());
        return new AuthorContext(nicknames, images, contributionService.getTierInfo(ids, staffIds));
    }

    public Map<String, Object> post(Post post, AuthorContext context, Integer viewerId, boolean detail) {
        User author = post.getAuthor();
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("id", post.getId());
        body.put("author", author.getId());
        body.put("author_username", author.getUsername());
        body.put("author_nickname", nicknameOf(context, author));
        body.put("author_profile_image_url", fileUrl(context.profileImages().get(author.getId())));
        putTier(body, context, author.getId());
        body.put("board_type", post.getBoardType());
        body.put("title", post.getTitle());
        if (detail) {
            body.put("content", post.getContent());
        }
        body.put("image", post.getImage());
        body.put("image_url", fileUrl(post.getImage()));
        body.put("view_count", post.getViewCount());
        body.put("is_pinned", post.isPinned());
        body.put("comments_count", commentRepository.countByPostId(post.getId()));
        body.put("likes_count", postLikeRepository.countByPostId(post.getId()));
        body.put("is_liked", viewerId != null
                && postLikeRepository.findByPostIdAndUserId(post.getId(), viewerId).isPresent());
        body.put("is_edited", edited(post.getCreatedAt(), post.getUpdatedAt()));
        body.put("created_at", post.getCreatedAt());
        body.put("updated_at", post.getUpdatedAt());
        return body;
    }

    public Map<String, Object> comment(Comment comment, AuthorContext context, Integer viewerId,
                                       List<Comment> replies) {
        User author = comment.getAuthor();
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("id", comment.getId());
        body.put("post", comment.getPost().getId());
        body.put("post_title", comment.getPost().getTitle());
        body.put("post_board_type", comment.getPost().getBoardType());
        body.put("author", author.getId());
        body.put("author_username", author.getUsername());
        body.put("author_nickname", nicknameOf(context, author));
        body.put("author_profile_image_url", fileUrl(context.profileImages().get(author.getId())));
        putTier(body, context, author.getId());
        body.put("parent", comment.getParent() == null ? null : comment.getParent().getId());
        body.put("content", comment.getContent());
        body.put("likes_count", commentLikeRepository.countByCommentId(comment.getId()));
        body.put("dislikes_count", commentDislikeRepository.countByCommentId(comment.getId()));
        body.put("is_liked", viewerId != null
                && commentLikeRepository.findByCommentIdAndUserId(comment.getId(), viewerId).isPresent());
        body.put("is_disliked", viewerId != null
                && commentDislikeRepository.findByCommentIdAndUserId(comment.getId(), viewerId).isPresent());
        body.put("is_edited", edited(comment.getCreatedAt(), comment.getUpdatedAt()));
        body.put("created_at", comment.getCreatedAt());
        body.put("updated_at", comment.getUpdatedAt());
        List<Map<String, Object>> replyBodies = new ArrayList<>();
        if (replies != null) {
            for (Comment reply : replies) {
                replyBodies.add(comment(reply, context, viewerId, null));
            }
        }
        body.put("replies", replyBodies);
        return body;
    }

    private void putTier(Map<String, Object> body, AuthorContext context, Integer authorId) {
        ContributionService.TierInfo tier = context.tiers().get(authorId);
        body.put("author_tier", tier == null ? "iron" : tier.tier());
        body.put("author_tier_label", tier == null ? "아이언" : tier.tierLabel());
        body.put("author_nickname_color", tier == null ? "#8b8b8b" : tier.nicknameColor());
    }

    private String nicknameOf(AuthorContext context, User author) {
        String nickname = context.nicknames().get(author.getId());
        // 프로필이 아직 없으면 Django 는 아이디로 만들어 줍니다. 여기서는 읽기만 하므로 아이디를 씁니다.
        return nickname != null ? nickname : author.getUsername();
    }

    /** 저장소 키를 브라우저가 열 수 있는 주소로 바꿉니다. 비어 있으면 빈 문자열입니다. */
    public String fileUrl(String key) {
        if (key == null || key.isBlank()) {
            return "";
        }
        if (key.startsWith("http://") || key.startsWith("https://")) {
            return key;
        }
        return mediaBaseUrl.isEmpty() ? key : mediaBaseUrl + "/" + key.replaceAll("^/+", "");
    }

    /**
     * 수정 여부입니다.
     *
     * 생성 직후에도 두 시각이 미세하게 다를 수 있어 Django 와 같이 1초 여유를 둡니다.
     */
    public boolean edited(java.time.OffsetDateTime createdAt, java.time.OffsetDateTime updatedAt) {
        if (createdAt == null || updatedAt == null) {
            return false;
        }
        return updatedAt.isAfter(createdAt.plus(Duration.ofSeconds(1)));
    }
}
