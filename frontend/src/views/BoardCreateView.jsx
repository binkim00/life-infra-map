import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { createPost } from '@/api/boards'
import { useAuthStore } from '@/stores/auth'

import styles from './BoardCreateView.module.css'

const BoardCreateView = () => {
  const navigate = useNavigate()
  const { boardType: boardTypeParam } = useParams()
  const boardType = boardTypeParam || 'free'

  const isLoggedIn = useAuthStore((state) => state.isLoggedIn)
  const user = useAuthStore((state) => state.user)

  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [imageFile, setImageFile] = useState(null)
  const [imagePreviewUrl, setImagePreviewUrl] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const boardTitle = boardType === 'notice' ? '공지사항' : '자유게시판'

  // 공지사항은 관리자만 쓸 수 있습니다.
  useEffect(() => {
    if (boardType === 'notice' && !user?.is_staff) {
      navigate('/boards/notice', { replace: true })
    }
  }, [boardType, user?.is_staff, navigate])

  useEffect(() => {
    if (!imagePreviewUrl) return undefined

    return () => {
      URL.revokeObjectURL(imagePreviewUrl)
    }
  }, [imagePreviewUrl])

  const handleImageChange = (event) => {
    const file = event.target.files?.[0]

    setImageFile(file || null)
    setImagePreviewUrl(file ? URL.createObjectURL(file) : '')
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setErrorMessage('')

    if (!isLoggedIn) {
      navigate('/login')
      return
    }

    if (!title.trim() || !content.trim()) {
      setErrorMessage('제목과 내용을 입력해주세요.')
      return
    }

    try {
      setIsLoading(true)

      const payload = new FormData()
      payload.append('board_type', boardType)
      payload.append('title', title)
      payload.append('content', content)

      if (imageFile) {
        payload.append('image', imageFile)
      }

      const response = await createPost(payload)

      navigate(`/boards/${response.data.board_type}/${response.data.id}`)
    } catch (error) {
      console.error(error)
      setErrorMessage(error.response?.data?.detail || '게시글 작성에 실패했습니다.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <main className={styles.boardPage}>
      <section className={styles.writeContainer}>
        <header className={styles.writeHeader}>
          <div>
            <p className={styles.eyebrow}>WRITE</p>
            <h1>{boardTitle} 글쓰기</h1>
          </div>

          <Link to={`/boards/${boardType}`} className={styles.backButton}>
            목록으로
          </Link>
        </header>

        <form className={styles.writeForm} onSubmit={handleSubmit}>
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            type="text"
            placeholder="제목을 입력하세요"
          />

          <textarea
            value={content}
            onChange={(event) => setContent(event.target.value)}
            rows={12}
            placeholder="내용을 입력하세요"
          />

          <label className={styles.imageField}>
            <span>이미지 첨부</span>
            <input type="file" accept="image/*" onChange={handleImageChange} />
          </label>

          {imagePreviewUrl ? (
            <img
              src={imagePreviewUrl}
              alt="첨부 이미지 미리보기"
              className={styles.imagePreview}
            />
          ) : null}

          {errorMessage ? <p className={styles.errorText}>{errorMessage}</p> : null}

          <button type="submit" disabled={isLoading}>
            {isLoading ? '작성 중...' : '등록하기'}
          </button>
        </form>
      </section>
    </main>
  )
}

export default BoardCreateView
