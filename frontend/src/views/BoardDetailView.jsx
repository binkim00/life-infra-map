import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

import {
  createComment,
  deleteComment,
  deletePost,
  getPost,
  reportComment,
  reportPost,
  toggleCommentDislike,
  toggleCommentLike,
  togglePostLike,
  updateComment,
} from '@/api/boards'
import { useAuthStore } from '@/stores/auth'
import { getTierIcon } from '@/utils/tierIcons'

import styles from './BoardDetailView.module.css'

const formatDateTime = (value) => {
  if (!value) {
    return ''
  }

  return new Date(value).toLocaleString('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const formatCommentTime = (value) => {
  if (!value) {
    return ''
  }

  const createdAt = new Date(value)
  const diffMinutes = Math.floor((Date.now() - createdAt.getTime()) / 60000)

  if (diffMinutes < 1) return '방금 전'
  if (diffMinutes < 60) return `${diffMinutes}분 전`

  const diffHours = Math.floor(diffMinutes / 60)
  if (diffHours < 24) return `${diffHours}시간 전`

  const diffDays = Math.floor(diffHours / 24)
  if (diffDays < 7) return `${diffDays}일 전`

  return createdAt.toLocaleDateString('ko-KR', {
    month: '2-digit',
    day: '2-digit',
  }).replace(/\. /g, '.').replace(/\.$/, '')
}

const getNicknameColorStyle = (author) => (
  author?.author_nickname_color ? { color: author.author_nickname_color } : undefined
)

/** 댓글/답글 어느 쪽이든 id 로 찾아 바꿔 줍니다. */
const mapCommentTree = (comments, commentId, updater) => comments.map((comment) => {
  if (comment.id === commentId) {
    return updater(comment)
  }

  if (comment.replies?.length) {
    const nextReplies = comment.replies.map((reply) => (
      reply.id === commentId ? updater(reply) : reply
    ))

    if (nextReplies.some((reply, index) => reply !== comment.replies[index])) {
      return { ...comment, replies: nextReplies }
    }
  }

  return comment
})

/** 지운 댓글과 그 답글 수를 함께 돌려줍니다. */
const removeCommentFromTree = (comments, commentId) => {
  const topLevelIndex = comments.findIndex((comment) => comment.id === commentId)

  if (topLevelIndex !== -1) {
    const removedCount = 1 + (comments[topLevelIndex].replies?.length || 0)

    return {
      comments: comments.filter((_, index) => index !== topLevelIndex),
      removedCount,
    }
  }

  let removedCount = 0
  const nextComments = comments.map((comment) => {
    if (!comment.replies?.some((reply) => reply.id === commentId)) {
      return comment
    }

    removedCount = 1

    return {
      ...comment,
      replies: comment.replies.filter((reply) => reply.id !== commentId),
    }
  })

  return { comments: nextComments, removedCount }
}

const CommentMoreMenu = ({
  comment,
  canEdit,
  canReport,
  isOpen,
  onToggle,
  onEdit,
  onDelete,
  onReport,
  ariaLabel,
}) => (
  <div
    className={`${styles.commentMoreMenu}${isOpen ? ` ${styles.open}` : ''}`}
    onClick={(event) => event.stopPropagation()}
  >
    <button
      type="button"
      className={styles.commentMoreButton}
      aria-label={ariaLabel}
      onClick={() => onToggle(comment.id)}
    >
      ⋮
    </button>

    {isOpen ? (
      <div className={styles.commentMenuDropdown}>
        {canEdit ? (
          <button type="button" onClick={() => onEdit(comment)}>수정</button>
        ) : null}
        {canEdit ? (
          <button type="button" className={styles.danger} onClick={() => onDelete(comment)}>
            삭제
          </button>
        ) : null}
        {canReport ? (
          <button type="button" onClick={() => onReport('comment', comment)}>신고하기</button>
        ) : null}
      </div>
    ) : null}
  </div>
)

const BoardDetailView = () => {
  const navigate = useNavigate()
  const location = useLocation()
  const { boardType: boardTypeParam, postId } = useParams()
  const boardType = boardTypeParam || 'free'

  const currentUser = useAuthStore((state) => state.user)

  const [post, setPost] = useState(null)
  const [commentContent, setCommentContent] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [reportTarget, setReportTarget] = useState(null)
  const [reportReason, setReportReason] = useState('')
  const [reportMessage, setReportMessage] = useState('')
  const [isSubmittingReport, setIsSubmittingReport] = useState(false)
  const [editingCommentId, setEditingCommentId] = useState(null)
  const [editingCommentContent, setEditingCommentContent] = useState('')
  const [replyingCommentId, setReplyingCommentId] = useState(null)
  const [replyContent, setReplyContent] = useState('')
  const [collapsedReplyIds, setCollapsedReplyIds] = useState(() => new Set())
  const [openCommentMenuId, setOpenCommentMenuId] = useState(null)

  const hasScrolledToHashRef = useRef(false)

  const boardTitle = boardType === 'notice' ? '공지사항' : '자유게시판'

  useEffect(() => {
    let isStale = false

    const fetchPost = async () => {
      try {
        setIsLoading(true)
        setErrorMessage('')

        const response = await getPost(postId)
        if (isStale) return
        setPost(response.data)
        hasScrolledToHashRef.current = false
      } catch (error) {
        if (isStale) return
        console.error(error)
        setErrorMessage('게시글을 불러오지 못했습니다.')
      } finally {
        if (!isStale) {
          setIsLoading(false)
        }
      }
    }

    fetchPost()

    return () => {
      isStale = true
    }
  }, [postId])

  // 알림에서 #comment-12 로 들어오면 해당 댓글까지 스크롤합니다.
  useEffect(() => {
    if (!post || !location.hash?.startsWith('#comment-')) return
    if (hasScrolledToHashRef.current) return

    const target = document.querySelector(location.hash)

    if (target) {
      hasScrolledToHashRef.current = true
      target.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [post, location.hash])

  const closeCommentMenu = useCallback(() => {
    setOpenCommentMenuId(null)
  }, [])

  useEffect(() => {
    document.addEventListener('click', closeCommentMenu)

    return () => {
      document.removeEventListener('click', closeCommentMenu)
    }
  }, [closeCommentMenu])

  const requireLogin = () => {
    if (!useAuthStore.getState().isLoggedIn) {
      navigate('/login')
      return false
    }

    return true
  }

  const handlePostLike = async () => {
    if (!requireLogin()) return

    const response = await togglePostLike(post.id)

    setPost((current) => ({
      ...current,
      is_liked: response.data.liked,
      likes_count: response.data.likes_count,
    }))
  }

  const handleCreateComment = async (event) => {
    event.preventDefault()

    if (!requireLogin()) return
    if (!commentContent.trim()) return

    const response = await createComment(post.id, { content: commentContent })
    const newComment = { ...response.data, replies: response.data.replies || [] }

    setPost((current) => ({
      ...current,
      comments: [...current.comments, newComment],
      comments_count: current.comments_count + 1,
    }))
    setCommentContent('')
  }

  const startReplyComment = (comment) => {
    if (!requireLogin()) return

    setReplyingCommentId(comment.id)
    setReplyContent('')
  }

  const cancelReplyComment = () => {
    setReplyingCommentId(null)
    setReplyContent('')
  }

  const handleCreateReply = async (event, comment) => {
    event.preventDefault()

    if (!replyContent.trim()) return

    const response = await createComment(post.id, {
      content: replyContent,
      parent: comment.id,
    })

    setPost((current) => ({
      ...current,
      comments: current.comments.map((item) => (
        item.id === comment.id
          ? { ...item, replies: [...(item.replies || []), response.data] }
          : item
      )),
      comments_count: current.comments_count + 1,
    }))
    cancelReplyComment()
  }

  const applyReaction = (commentId, data) => {
    setPost((current) => ({
      ...current,
      comments: mapCommentTree(current.comments, commentId, (comment) => ({
        ...comment,
        is_liked: data.liked,
        is_disliked: data.disliked,
        likes_count: data.likes_count,
        dislikes_count: data.dislikes_count,
      })),
    }))
  }

  const handleCommentLike = async (comment) => {
    if (!requireLogin()) return

    const response = await toggleCommentLike(comment.id)
    applyReaction(comment.id, response.data)
  }

  const handleCommentDislike = async (comment) => {
    if (!requireLogin()) return

    const response = await toggleCommentDislike(comment.id)
    applyReaction(comment.id, response.data)
  }

  const toggleReplies = (commentId) => {
    setCollapsedReplyIds((current) => {
      const next = new Set(current)

      if (next.has(commentId)) {
        next.delete(commentId)
      } else {
        next.add(commentId)
      }

      return next
    })
  }

  const areRepliesVisible = (commentId) => !collapsedReplyIds.has(commentId)

  const toggleCommentMenu = (commentId) => {
    setOpenCommentMenuId((current) => (current === commentId ? null : commentId))
  }

  const handleDeletePost = async () => {
    if (!confirm('게시글을 삭제하시겠습니까?')) {
      return
    }

    await deletePost(post.id)
    navigate(`/boards/${boardType}`)
  }

  const handleDeleteComment = async (comment) => {
    if (!confirm('댓글을 삭제하시겠습니까?')) {
      return
    }

    closeCommentMenu()
    await deleteComment(comment.id)

    setPost((current) => {
      const { comments, removedCount } = removeCommentFromTree(current.comments, comment.id)

      return {
        ...current,
        comments,
        comments_count: current.comments_count - removedCount,
      }
    })
  }

  const startEditComment = (comment) => {
    closeCommentMenu()
    setEditingCommentId(comment.id)
    setEditingCommentContent(comment.content)
  }

  const cancelEditComment = () => {
    setEditingCommentId(null)
    setEditingCommentContent('')
  }

  const handleUpdateComment = async (event, comment) => {
    event.preventDefault()

    if (!editingCommentContent.trim()) return

    const response = await updateComment(comment.id, {
      content: editingCommentContent,
    })

    setPost((current) => ({
      ...current,
      comments: mapCommentTree(current.comments, comment.id, (item) => ({
        ...response.data,
        // 서버 응답에 답글이 없으면 화면에 있던 답글을 유지합니다.
        replies: item.replies || response.data.replies || [],
      })),
    }))
    cancelEditComment()
  }

  const openReportModal = (type, target) => {
    if (!requireLogin()) return

    closeCommentMenu()
    setReportTarget({ type, target })
    setReportReason('')
    setReportMessage('')
  }

  const closeReportModal = () => {
    setReportTarget(null)
    setReportReason('')
    setReportMessage('')
    setIsSubmittingReport(false)
  }

  const submitReport = async (event) => {
    event.preventDefault()

    if (!reportTarget || isSubmittingReport) {
      return
    }

    if (!reportReason.trim()) {
      setReportMessage('신고 사유를 입력해주세요.')
      return
    }

    try {
      setIsSubmittingReport(true)
      setReportMessage('')

      const payload = { reason: reportReason }

      if (reportTarget.type === 'post') {
        await reportPost(reportTarget.target.id, payload)
      } else {
        await reportComment(reportTarget.target.id, payload)
      }

      alert('신고가 접수되었습니다.')
      closeReportModal()
    } catch (error) {
      console.error(error)
      setReportMessage(error.response?.data?.detail || '신고 접수에 실패했습니다.')
    } finally {
      setIsSubmittingReport(false)
    }
  }

  // 최상위 댓글은 이 안에 답글 입력/목록까지 들어가므로 children 으로 받습니다.
  const renderCommentBody = (comment, { isReply = false, children = null } = {}) => (
    <div className={styles.commentBody}>
      <div className={styles.commentMetaLine}>
        <strong style={getNicknameColorStyle(comment)}>
          {comment.author_nickname || comment.author_username}
        </strong>
        {comment.author_tier ? (
          <img
            src={getTierIcon(comment.author_tier)}
            alt={comment.author_tier_label || comment.author_tier}
            className={`${styles.tierIcon} ${styles.small}`}
          />
        ) : null}
        <span>{formatCommentTime(comment.created_at)}</span>
        {comment.is_edited ? <span>(수정됨)</span> : null}
      </div>

      {editingCommentId === comment.id ? (
        <form
          className={styles.commentEditForm}
          onSubmit={(event) => handleUpdateComment(event, comment)}
        >
          <textarea
            value={editingCommentContent}
            onChange={(event) => setEditingCommentContent(event.target.value)}
            rows={3}
          />

          <div className={styles.commentEditActions}>
            <button
              type="button"
              className={styles.commentCancelButton}
              onClick={cancelEditComment}
            >
              취소
            </button>

            <button type="submit" className={styles.commentSaveButton}>저장</button>
          </div>
        </form>
      ) : (
        <p className={styles.commentContent}>{comment.content}</p>
      )}

      <div className={styles.commentActions}>
        <button
          type="button"
          className={`${styles.iconActionButton}${comment.is_liked ? ` ${styles.active}` : ''}`}
          onClick={() => handleCommentLike(comment)}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M7 10v10" />
            <path d="M15 5.5 14 10h5.5a2 2 0 0 1 2 2.3l-1 6A2 2 0 0 1 18.5 20H7V10h3l3.2-5.1A1 1 0 0 1 15 5.5Z" />
          </svg>
          <span>{comment.likes_count}</span>
        </button>

        <button
          type="button"
          className={`${styles.iconActionButton}${comment.is_disliked ? ` ${styles.active}` : ''}`}
          onClick={() => handleCommentDislike(comment)}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M17 14V4" />
            <path d="M9 18.5 10 14H4.5a2 2 0 0 1-2-2.3l1-6A2 2 0 0 1 5.5 4H17v10h-3l-3.2 5.1A1 1 0 0 1 9 18.5Z" />
          </svg>
          <span>{comment.dislikes_count}</span>
        </button>

        {!isReply ? (
          <button
            type="button"
            className={styles.textActionButton}
            onClick={() => startReplyComment(comment)}
          >
            답글
          </button>
        ) : null}
      </div>

      {children}
    </div>
  )

  return (
    <main className={styles.boardPage}>
      <section className={styles.detailContainer}>
        <header className={styles.detailHeader}>
          <div>
            <p className={styles.eyebrow}>DETAIL</p>
            <h1>{boardTitle}</h1>
          </div>

          <Link to={`/boards/${boardType}`} className={styles.backButton}>
            목록으로
          </Link>
        </header>

        {isLoading ? (
          <p className={styles.statusText}>게시글을 불러오는 중입니다.</p>
        ) : errorMessage ? (
          <p className={styles.errorText}>{errorMessage}</p>
        ) : post ? (
          <article className={styles.postDetailCard}>
            <div className={styles.postTitleRow}>
              <div>
                <span className={styles.boardBadge}>
                  {post.board_type === 'notice' ? '공지' : '자유'}
                </span>

                <h2>{post.title}</h2>
              </div>

              {currentUser?.id === post.author ? (
                <div className={styles.postManageButtons}>
                  <Link
                    to={`/boards/${boardType}/${post.id}/edit`}
                    className={styles.editButton}
                  >
                    수정
                  </Link>

                  <button
                    type="button"
                    className={styles.deleteButton}
                    onClick={handleDeletePost}
                  >
                    삭제
                  </button>
                </div>
              ) : null}
            </div>

            <div className={styles.postMeta}>
              <span className={styles.authorChip}>
                <span className={styles.authorAvatar}>
                  {post.author_profile_image_url ? (
                    <img src={post.author_profile_image_url} alt={post.author_nickname} />
                  ) : (
                    <span className={styles.defaultAvatar} aria-hidden="true" />
                  )}
                </span>
                <span style={getNicknameColorStyle(post)}>{post.author_nickname}</span>
                {post.author_tier ? (
                  <img
                    src={getTierIcon(post.author_tier)}
                    alt={post.author_tier_label || post.author_tier}
                    className={styles.tierIcon}
                  />
                ) : null}
              </span>
              <span>
                {formatDateTime(post.created_at)}
                {post.is_edited ? ' (수정됨)' : ''}
              </span>
              <span>조회 {post.view_count}</span>
              <span>댓글 {post.comments_count}</span>
              <span>좋아요 {post.likes_count}</span>
            </div>

            {post.image_url ? (
              <img src={post.image_url} alt={post.title} className={styles.postImage} />
            ) : null}

            <div className={styles.postContent}>{post.content}</div>

            <div className={styles.reactionBox}>
              <div className={styles.reactionStats}>
                <strong className={styles.postLikeCount}>{post.likes_count}</strong>

                <span className={styles.commentCount}>💬 {post.comments_count}</span>
              </div>

              <button
                type="button"
                className={`${styles.circleLikeButton}${post.is_liked ? ` ${styles.active}` : ''}`}
                onClick={handlePostLike}
              >
                <span className={styles.starIcon}>★</span>

                <span className={styles.circleLikeLabel}>
                  {post.is_liked ? '취소' : '좋아요'}
                </span>
              </button>

              {post.board_type === 'free' ? (
                <button
                  type="button"
                  className={styles.reportButton}
                  onClick={() => openReportModal('post', post)}
                >
                  신고하기
                </button>
              ) : null}
            </div>

            <section className={styles.commentSection}>
              <h3>댓글 {post.comments_count}</h3>

              <form className={styles.commentForm} onSubmit={handleCreateComment}>
                <textarea
                  value={commentContent}
                  onChange={(event) => setCommentContent(event.target.value)}
                  rows={3}
                  placeholder="댓글을 입력하세요"
                />

                <button type="submit">댓글 등록</button>
              </form>

              <div className={styles.commentList}>
                {post.comments.map((comment) => (
                  <article
                    key={comment.id}
                    id={`comment-${comment.id}`}
                    className={styles.commentCard}
                  >
                    <div className={styles.commentItem}>
                      <span className={styles.commentAvatar}>
                        {comment.author_profile_image_url ? (
                          <img
                            src={comment.author_profile_image_url}
                            alt={comment.author_nickname}
                          />
                        ) : (
                          <span className={styles.defaultAvatar} aria-hidden="true" />
                        )}
                      </span>

                      {renderCommentBody(comment, { children: (
                        <>
                          {replyingCommentId === comment.id ? (
                          <form
                            className={styles.replyForm}
                            onSubmit={(event) => handleCreateReply(event, comment)}
                          >
                            <textarea
                              value={replyContent}
                              onChange={(event) => setReplyContent(event.target.value)}
                              rows={2}
                              placeholder="답글을 입력하세요"
                            />
                            <div className={styles.commentEditActions}>
                              <button
                                type="button"
                                className={styles.commentCancelButton}
                                onClick={cancelReplyComment}
                              >
                                취소
                              </button>
                              <button type="submit" className={styles.commentSaveButton}>
                                답글 등록
                              </button>
                            </div>
                          </form>
                        ) : null}

                        {comment.replies?.length ? (
                          <button
                            type="button"
                            className={styles.replyCountButton}
                            onClick={() => toggleReplies(comment.id)}
                          >
                            답글 {comment.replies.length}개
                            <span className={areRepliesVisible(comment.id) ? styles.open : undefined}>
                              ⌄
                            </span>
                          </button>
                        ) : null}

                        {comment.replies?.length && areRepliesVisible(comment.id) ? (
                          <div className={styles.replyList}>
                            {comment.replies.map((reply) => (
                              <article
                                key={reply.id}
                                id={`comment-${reply.id}`}
                                className={styles.replyCard}
                              >
                                <span className={`${styles.commentAvatar} ${styles.small}`}>
                                  {reply.author_profile_image_url ? (
                                    <img
                                      src={reply.author_profile_image_url}
                                      alt={reply.author_nickname}
                                    />
                                  ) : (
                                    <span className={styles.defaultAvatar} aria-hidden="true" />
                                  )}
                                </span>

                                {renderCommentBody(reply, { isReply: true })}

                                {currentUser?.id === reply.author || post.board_type === 'free' ? (
                                  <CommentMoreMenu
                                    comment={reply}
                                    canEdit={currentUser?.id === reply.author}
                                    canReport={post.board_type === 'free'}
                                    isOpen={openCommentMenuId === reply.id}
                                    onToggle={toggleCommentMenu}
                                    onEdit={startEditComment}
                                    onDelete={handleDeleteComment}
                                    onReport={openReportModal}
                                    ariaLabel="답글 메뉴 열기"
                                  />
                                ) : null}
                              </article>
                            ))}
                          </div>
                          ) : null}
                        </>
                      ) })}

                      {currentUser?.id === comment.author || post.board_type === 'free' ? (
                        <CommentMoreMenu
                          comment={comment}
                          canEdit={currentUser?.id === comment.author}
                          canReport={post.board_type === 'free'}
                          isOpen={openCommentMenuId === comment.id}
                          onToggle={toggleCommentMenu}
                          onEdit={startEditComment}
                          onDelete={handleDeleteComment}
                          onReport={openReportModal}
                          ariaLabel="댓글 메뉴 열기"
                        />
                      ) : null}
                    </div>
                  </article>
                ))}

                {post.comments.length === 0 ? (
                  <p className={styles.emptyText}>아직 댓글이 없습니다.</p>
                ) : null}
              </div>
            </section>
          </article>
        ) : null}
      </section>

      {reportTarget ? (
        <div
          className={styles.reportModalBackdrop}
          onClick={(event) => {
            if (event.target === event.currentTarget) {
              closeReportModal()
            }
          }}
        >
          <form className={styles.reportModal} onSubmit={submitReport}>
            <header>
              <div>
                <p className={styles.modalLabel}>REPORT</p>
                <h2>신고 사유</h2>
              </div>

              <button
                type="button"
                className={styles.modalCloseButton}
                onClick={closeReportModal}
              >
                ×
              </button>
            </header>

            <p className={styles.reportTargetText}>
              {reportTarget.type === 'post' ? '게시글' : '댓글'}을 신고합니다.
            </p>

            <textarea
              value={reportReason}
              onChange={(event) => setReportReason(event.target.value)}
              rows={5}
              placeholder="신고 사유를 입력하세요"
            />

            {reportMessage ? (
              <p className={styles.reportMessage}>{reportMessage}</p>
            ) : null}

            <div className={styles.modalActions}>
              <button
                type="button"
                className={styles.modalCancelButton}
                onClick={closeReportModal}
              >
                취소
              </button>

              <button
                type="submit"
                className={styles.modalSubmitButton}
                disabled={isSubmittingReport}
              >
                {isSubmittingReport ? '제출 중' : '제출'}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </main>
  )
}

export default BoardDetailView
