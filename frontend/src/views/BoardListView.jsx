import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { getPosts } from '@/api/boards'
import { useAuthStore } from '@/stores/auth'
import { getTierIcon } from '@/utils/tierIcons'

import styles from './BoardListView.module.css'

const PAGE_SIZE = 10

const formatBoardDate = (value) => {
  if (!value) {
    return ''
  }

  const date = new Date(value)
  const now = new Date()
  const isToday = date.toDateString() === now.toDateString()

  if (isToday) {
    return date.toLocaleTimeString('ko-KR', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    })
  }

  return date.toLocaleDateString('ko-KR', {
    month: '2-digit',
    day: '2-digit',
  }).replace(/\. /g, '.').replace(/\.$/, '')
}

const getAuthorInitial = (post) => {
  const name = post.author_nickname || post.author_username || '?'
  return name.slice(0, 1)
}

const buildPageNumbers = (total, current) => {
  const pages = []

  if (total <= 7) {
    for (let page = 1; page <= total; page += 1) pages.push(page)
    return pages
  }

  pages.push(1)

  const start = Math.max(2, current - 1)
  const end = Math.min(total - 1, current + 1)

  if (start > 2) pages.push('start-ellipsis')

  for (let page = start; page <= end; page += 1) pages.push(page)

  if (end < total - 1) pages.push('end-ellipsis')

  pages.push(total)
  return pages
}

const BoardListView = () => {
  const { boardType: boardTypeParam } = useParams()
  const boardType = boardTypeParam || 'free'

  const isLoggedIn = useAuthStore((state) => state.isLoggedIn)
  const user = useAuthStore((state) => state.user)

  const [posts, setPosts] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [sortMode, setSortMode] = useState('latest')
  const [currentPage, setCurrentPage] = useState(1)

  // 게시판 종류가 바뀌면 목록을 다시 받습니다. 로그인 없이도 조회됩니다.
  useEffect(() => {
    let isStale = false

    const fetchPosts = async () => {
      try {
        setIsLoading(true)
        setErrorMessage('')

        const response = await getPosts(boardType)

        if (isStale) return

        setPosts(response.data)
        setCurrentPage(1)
      } catch (error) {
        if (isStale) return
        console.error(error)
        setErrorMessage('게시글 목록을 불러오지 못했습니다.')
      } finally {
        if (!isStale) {
          setIsLoading(false)
        }
      }
    }

    fetchPosts()

    return () => {
      isStale = true
    }
  }, [boardType])

  useEffect(() => {
    setCurrentPage(1)
  }, [searchQuery, sortMode])

  const boardTitle = boardType === 'notice' ? '공지사항' : '전체 게시판'

  const filteredPosts = useMemo(() => {
    const keyword = searchQuery.trim().toLowerCase()

    if (!keyword) {
      return posts
    }

    return posts.filter((post) => (
      [post.title, post.author_nickname, post.author_username]
        .some((value) => String(value || '').toLowerCase().includes(keyword))
    ))
  }, [posts, searchQuery])

  const sortedPosts = useMemo(() => {
    const nextPosts = [...filteredPosts]

    nextPosts.sort((a, b) => {
      if (a.is_pinned !== b.is_pinned) {
        return Number(b.is_pinned) - Number(a.is_pinned)
      }

      if (sortMode === 'likes') {
        return (b.likes_count || 0) - (a.likes_count || 0)
      }

      if (sortMode === 'comments') {
        return (b.comments_count || 0) - (a.comments_count || 0)
      }

      return new Date(b.created_at || 0) - new Date(a.created_at || 0)
    })

    return nextPosts
  }, [filteredPosts, sortMode])

  const totalPages = Math.max(1, Math.ceil(sortedPosts.length / PAGE_SIZE))

  // 검색으로 목록이 줄면 현재 페이지가 범위를 벗어날 수 있습니다.
  const safeCurrentPage = Math.min(currentPage, totalPages)

  const paginatedPosts = useMemo(() => {
    const start = (safeCurrentPage - 1) * PAGE_SIZE
    return sortedPosts.slice(start, start + PAGE_SIZE)
  }, [sortedPosts, safeCurrentPage])

  const pageNumbers = useMemo(
    () => buildPageNumbers(totalPages, safeCurrentPage),
    [totalPages, safeCurrentPage],
  )

  const canWritePost = isLoggedIn && (boardType !== 'notice' || user?.is_staff)

  const goToPage = (page) => {
    if (page < 1 || page > totalPages) {
      return
    }

    setCurrentPage(page)
  }

  return (
    <main className={styles.boardPage}>
      <section className={styles.boardContainer}>
        <header className={styles.boardHeader}>
          <div className={styles.boardTitleGroup}>
            <h1>{boardTitle}</h1>
            <span>{`총 ${filteredPosts.length.toLocaleString('ko-KR')}개`}</span>
          </div>

          <div className={styles.boardActions}>
            <label className={styles.searchField}>
              <input
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                type="search"
                placeholder="제목, 작성자 검색"
              />
              <span aria-hidden="true">⌕</span>
            </label>

            <select
              value={sortMode}
              onChange={(event) => setSortMode(event.target.value)}
              className={styles.sortSelect}
              aria-label="게시글 정렬"
            >
              <option value="latest">최신순</option>
              <option value="comments">댓글순</option>
              <option value="likes">좋아요순</option>
            </select>

            {canWritePost ? (
              <Link to={`/boards/${boardType}/write`} className={styles.writeButton}>
                글쓰기
              </Link>
            ) : boardType !== 'notice' ? (
              <Link to="/login" className={styles.writeButton}>
                로그인
              </Link>
            ) : null}
          </div>
        </header>

        {isLoading ? (
          <p className={styles.statusText}>게시글을 불러오는 중입니다.</p>
        ) : errorMessage ? (
          <p className={styles.errorText}>{errorMessage}</p>
        ) : (
          <section className={styles.boardTableWrap}>
            <table className={styles.boardTable}>
              <colgroup>
                <col className={styles.colTitle} />
                <col className={styles.colAuthor} />
                <col className={styles.colDate} />
                <col className={styles.colCount} />
                <col className={styles.colCount} />
              </colgroup>

              <thead>
                <tr>
                  <th>제목</th>
                  <th>작성자</th>
                  <th>작성일</th>
                  <th>댓글</th>
                  <th>좋아요</th>
                </tr>
              </thead>

              <tbody>
                {paginatedPosts.map((post) => (
                  <tr key={post.id} className={post.is_pinned ? styles.pinned : undefined}>
                    <td className={styles.titleCell}>
                      <Link
                        to={`/boards/${post.board_type}/${post.id}`}
                        className={styles.titleLink}
                      >
                        {post.board_type === 'notice' || post.is_pinned ? (
                          <span className={styles.noticeBadge}>공지</span>
                        ) : null}
                        <span className={styles.titleText}>{post.title}</span>
                        {post.is_pinned ? (
                          <span className={styles.pinMark} aria-label="고정됨">◆</span>
                        ) : null}
                      </Link>
                    </td>
                    <td className={styles.authorCell} data-label="작성자">
                      <span className={styles.authorChip}>
                        <span className={styles.authorAvatar}>
                          {post.author_profile_image_url ? (
                            <img
                              src={post.author_profile_image_url}
                              alt={post.author_nickname}
                            />
                          ) : (
                            <span className={styles.defaultAvatar} aria-hidden="true">
                              {getAuthorInitial(post)}
                            </span>
                          )}
                        </span>
                        <span
                          className={styles.authorName}
                          style={post.author_nickname_color
                            ? { color: post.author_nickname_color }
                            : undefined}
                        >
                          {post.author_nickname}
                        </span>
                        {post.author_tier ? (
                          <img
                            src={getTierIcon(post.author_tier)}
                            alt={post.author_tier_label || post.author_tier}
                            className={styles.tierIcon}
                          />
                        ) : null}
                      </span>
                    </td>
                    <td data-label="작성일">{formatBoardDate(post.created_at)}</td>
                    <td data-label="댓글">
                      <span className={`${styles.metricCell} ${styles.comment}`}>
                        <svg className={styles.commentIcon} viewBox="0 0 24 24" aria-hidden="true">
                          <path
                            className={styles.commentIconBubble}
                            d="M4.7 16.1A8.5 8.5 0 0 1 3 11.1C3 6.4 7.1 2.8 12.2 2.8s9.2 3.6 9.2 8.3-4.1 8.3-9.2 8.3a10.4 10.4 0 0 1-3.7-.7 6.7 6.7 0 0 1-4.5 2l-.8-.1.5-.7a6.7 6.7 0 0 0 1-3.8Z"
                          />
                          <path
                            className={styles.commentIconDot}
                            d="M8.2 11.2h.1M12.2 11.2h.1M16.2 11.2h.1"
                          />
                        </svg>
                        {post.comments_count}
                      </span>
                    </td>
                    <td data-label="좋아요">
                      <span className={`${styles.metricCell} ${styles.like}`}>
                        <span aria-hidden="true">♥</span>
                        {post.likes_count}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {filteredPosts.length === 0 ? (
              <p className={styles.emptyText}>조건에 맞는 게시글이 없습니다.</p>
            ) : null}

            {filteredPosts.length > 0 ? (
              <nav className={styles.pagination} aria-label="게시글 페이지">
                <button
                  type="button"
                  disabled={safeCurrentPage === 1}
                  onClick={() => goToPage(safeCurrentPage - 1)}
                >
                  ‹
                </button>
                {pageNumbers.map((page) => (
                  typeof page === 'string' ? (
                    <span key={page} className={styles.pageEllipsis}>...</span>
                  ) : (
                    <button
                      key={page}
                      type="button"
                      className={page === safeCurrentPage ? styles.active : undefined}
                      onClick={() => goToPage(page)}
                    >
                      {page}
                    </button>
                  )
                ))}
                <button
                  type="button"
                  disabled={safeCurrentPage === totalPages}
                  onClick={() => goToPage(safeCurrentPage + 1)}
                >
                  ›
                </button>
              </nav>
            ) : null}
          </section>
        )}
      </section>
    </main>
  )
}

export default BoardListView
