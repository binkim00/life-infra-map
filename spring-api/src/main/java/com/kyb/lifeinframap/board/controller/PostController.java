package com.kyb.lifeinframap.board.controller;

import com.kyb.lifeinframap.board.domain.*;
import com.kyb.lifeinframap.board.repository.*;
import com.kyb.lifeinframap.board.service.*;
import com.kyb.lifeinframap.board.dto.*;

import com.kyb.lifeinframap.account.domain.User;
import com.kyb.lifeinframap.account.repository.UserRepository;
import jakarta.validation.constraints.NotBlank;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

/**
 * 게시글 API를 담당하는 Spring 엔드포인트입니다.
 *
 * 목록은 페이지네이션 없이 배열을 그대로 내려줍니다. Django 와 같은 형태입니다.
 */
@RestController
@RequestMapping("/api/boards/posts")
public class PostController {

    private final PostRepository postRepository;
    private final CommentRepository commentRepository;
    private final UserRepository userRepository;
    private final BoardResponseAssembler assembler;
    private final PenaltyService penaltyService;
    private final com.kyb.lifeinframap.storage.service.StorageService storageService;

    public PostController(
            PostRepository postRepository,
            CommentRepository commentRepository,
            UserRepository userRepository,
            BoardResponseAssembler assembler,
            PenaltyService penaltyService,
            com.kyb.lifeinframap.storage.service.StorageService storageService) {
        this.postRepository = postRepository;
        this.commentRepository = commentRepository;
        this.userRepository = userRepository;
        this.assembler = assembler;
        this.penaltyService = penaltyService;
        this.storageService = storageService;
    }


    @GetMapping
    @Transactional(readOnly = true)
    public List<Map<String, Object>> list(
            @RequestParam(name = "board_type", defaultValue = "free") String boardType,
            Authentication authentication) {

        // 자유게시판에는 고정된 공지도 함께 보여 줍니다. Django 와 같은 규칙입니다.
        List<Post> posts = "free".equals(boardType)
                ? postRepository.findAll(sort()).stream()
                        .filter(post -> "free".equals(post.getBoardType())
                                || ("notice".equals(post.getBoardType()) && post.isPinned()))
                        .toList()
                : postRepository.findAll(sort()).stream()
                        .filter(post -> boardType.equals(post.getBoardType()))
                        .toList();

        Integer viewerId = viewerId(authentication);
        BoardResponseAssembler.AuthorContext context =
                assembler.loadAuthors(posts.stream().map(Post::getAuthor).toList());

        List<Map<String, Object>> body = new ArrayList<>();
        for (Post post : posts) {
            body.add(assembler.post(post, context, viewerId, false));
        }
        return body;
    }

    /** 이미지를 함께 올리는 글쓰기입니다. 프론트가 FormData 로 보냅니다. */
    @PostMapping(consumes = org.springframework.http.MediaType.MULTIPART_FORM_DATA_VALUE)
    @Transactional
    public ResponseEntity<?> createMultipart(
            @RequestParam String title,
            @RequestParam String content,
            @RequestParam(name = "board_type", required = false) String boardType,
            @RequestParam(required = false) org.springframework.web.multipart.MultipartFile image,
            Authentication authentication) {
        String imageKey;
        try {
            imageKey = storageService.upload(image, com.kyb.lifeinframap.storage.service.StorageService.BOARD_IMAGE_PREFIX);
        } catch (IllegalArgumentException exception) {
            return ResponseEntity.badRequest().body(Map.of("image", List.of(exception.getMessage())));
        }
        return create(new PostRequest(title, content, boardType, imageKey), authentication);
    }

    @PostMapping
    @Transactional
    public ResponseEntity<?> create(@RequestBody PostRequest request, Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        UserPenalty penalty = penaltyService.findCurrent(user.getId());
        if (penalty != null) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN).body(penaltyService.blockedBody(penalty));
        }

        String boardType = request.boardType() == null || request.boardType().isBlank()
                ? "free" : request.boardType();
        if ("notice".equals(boardType) && !user.isStaff()) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN)
                    .body(Map.of("detail", "공지사항은 관리자만 작성할 수 있습니다."));
        }

        Post post = Post.create(user, boardType, request.title(), request.content(), request.image());
        // Django 는 공지를 항상 고정합니다.
        post.pin("notice".equals(boardType));
        postRepository.save(post);

        BoardResponseAssembler.AuthorContext context = assembler.loadAuthors(List.of(user));
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(assembler.post(post, context, user.getId(), true));
    }

    @GetMapping("/{postId}")
    @Transactional
    public ResponseEntity<?> detail(@PathVariable Long postId, Authentication authentication) {
        Post post = postRepository.findById(postId).orElse(null);
        if (post == null) {
            return notFound();
        }
        post.increaseViewCount();

        Integer viewerId = viewerId(authentication);
        BoardResponseAssembler.AuthorContext context = assembler.loadAuthors(authorsOf(post));

        Map<String, Object> body = assembler.post(post, context, viewerId, true);
        body.put("comments", commentTree(post, context, viewerId));
        return ResponseEntity.ok(body);
    }

    @PatchMapping("/{postId}")
    @Transactional
    public ResponseEntity<?> update(@PathVariable Long postId, @RequestBody PostRequest request,
                                    Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        Post post = postRepository.findById(postId).orElse(null);
        if (post == null) {
            return notFound();
        }
        if (!post.getAuthor().getId().equals(user.getId())) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN)
                    .body(Map.of("detail", "본인이 작성한 글만 수정할 수 있습니다."));
        }

        post.edit(request.title(), request.content(), request.image());
        BoardResponseAssembler.AuthorContext context = assembler.loadAuthors(List.of(post.getAuthor()));
        return ResponseEntity.ok(assembler.post(post, context, user.getId(), true));
    }

    /** 수정에서도 새 이미지를 선택할 수 있도록 글쓰기와 같은 multipart 계약을 제공합니다. */
    @PatchMapping(value = "/{postId}", consumes = org.springframework.http.MediaType.MULTIPART_FORM_DATA_VALUE)
    @Transactional
    public ResponseEntity<?> updateMultipart(
            @PathVariable Long postId,
            @RequestParam String title,
            @RequestParam String content,
            @RequestParam(name = "board_type", required = false) String boardType,
            @RequestParam(required = false) org.springframework.web.multipart.MultipartFile image,
            Authentication authentication) {
        String imageKey = null;
        if (image != null && !image.isEmpty()) {
            try {
                imageKey = storageService.upload(
                        image,
                        com.kyb.lifeinframap.storage.service.StorageService.BOARD_IMAGE_PREFIX);
            } catch (IllegalArgumentException exception) {
                return ResponseEntity.badRequest().body(Map.of("image", List.of(exception.getMessage())));
            }
        }
        return update(postId, new PostRequest(title, content, boardType, imageKey), authentication);
    }

    @DeleteMapping("/{postId}")
    @Transactional
    public ResponseEntity<?> delete(@PathVariable Long postId, Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        Post post = postRepository.findById(postId).orElse(null);
        if (post == null) {
            return notFound();
        }
        // 관리자는 남의 글도 지울 수 있습니다.
        if (!post.getAuthor().getId().equals(user.getId()) && !user.isStaff()) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN)
                    .body(Map.of("detail", "본인이 작성한 글만 삭제할 수 있습니다."));
        }
        postRepository.delete(post);
        return ResponseEntity.noContent().build();
    }

    private List<Map<String, Object>> commentTree(Post post, BoardResponseAssembler.AuthorContext context,
                                                  Integer viewerId) {
        List<Comment> all = commentRepository.findByPostIdOrderByCreatedAtAsc(post.getId());
        Map<Long, List<Comment>> repliesByParent = new LinkedHashMap<>();
        List<Comment> roots = new ArrayList<>();
        for (Comment comment : all) {
            if (comment.getParent() == null) {
                roots.add(comment);
            } else {
                repliesByParent.computeIfAbsent(comment.getParent().getId(), key -> new ArrayList<>())
                        .add(comment);
            }
        }
        List<Map<String, Object>> body = new ArrayList<>();
        for (Comment root : roots) {
            body.add(assembler.comment(root, context,
                    viewerId, repliesByParent.getOrDefault(root.getId(), List.of())));
        }
        return body;
    }

    private List<User> authorsOf(Post post) {
        List<User> authors = new ArrayList<>();
        authors.add(post.getAuthor());
        commentRepository.findByPostIdOrderByCreatedAtAsc(post.getId())
                .forEach(comment -> authors.add(comment.getAuthor()));
        return authors;
    }

    private Sort sort() {
        return Sort.by(Sort.Order.desc("pinned"), Sort.Order.desc("createdAt"), Sort.Order.desc("id"));
    }

    private Integer viewerId(Authentication authentication) {
        User user = currentUser(authentication);
        return user == null ? null : user.getId();
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
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("detail", "게시글을 찾을 수 없습니다."));
    }
}
