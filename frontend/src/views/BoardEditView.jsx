import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { getPost, updatePost } from '@/api/boards'
import { useAuthStore } from '@/stores/auth'

import styles from './BoardEditView.module.css'

const BoardEditView = () => {
  const navigate = useNavigate()
  const { boardType: boardTypeParam, postId } = useParams()
  const boardType = boardTypeParam || 'free'

  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [imageFile, setImageFile] = useState(null)
  const [imagePreviewUrl, setImagePreviewUrl] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const boardTitle = boardType === 'notice' ? '공지사항' : '자유게시판'

  useEffect(() => {
    let isStale = false

    const fetchPost = async () => {
      try {
        const response = await getPost(postId)
        const post = response.data

        if (isStale) return

        if (useAuthStore.getState().user?.id !== post.author) {
          alert('작성자만 수정할 수 있습니다.')
          navigate(`/boards/${boardType}/${postId}`)
          return
        }

        setTitle(post.title)
        setContent(post.content)
        setImagePreviewUrl(post.image_url || '')
      } catch (error) {
        if (isStale) return
        console.error(error)
        setErrorMessage('게시글을 불러오지 못했습니다.')
      }
    }

    fetchPost()

    return () => {
      isStale = true
    }
  }, [boardType, postId, navigate])

  const handleImageChange = (event) => {
    const file = event.target.files?.[0]

    setImageFile(file || null)

    if (file) {
      // 새 파일을 고르지 않으면 서버에 저장된 기존 이미지를 그대로 둡니다.
      setImagePreviewUrl((current) => {
        if (current?.startsWith('blob:')) {
          URL.revokeObjectURL(current)
        }

        return URL.createObjectURL(file)
      })
    }
  }

  useEffect(() => () => {
    if (imagePreviewUrl?.startsWith('blob:')) {
      URL.revokeObjectURL(imagePreviewUrl)
    }
  }, [imagePreviewUrl])

  const handleSubmit = async (event) => {
    event.preventDefault()
    setErrorMessage('')

    if (!title.trim() || !content.trim()) {
      setErrorMessage('제목과 내용을 입력해주세요.')
      return
    }

    try {
      setIsLoading(true)

      const payload = new FormData()
      payload.append('title', title)
      payload.append('content', content)
      payload.append('board_type', boardType)

      if (imageFile) {
        payload.append('image', imageFile)
      }

      const response = await updatePost(postId, payload)

      navigate(`/boards/${response.data.board_type}/${response.data.id}`)
    } catch (error) {
      console.error(error)
      setErrorMessage(error.response?.data?.detail || '게시글 수정에 실패했습니다.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <main className={styles.boardPage}>
      <section className={styles.writeContainer}>
        <header className={styles.writeHeader}>
          <div>
            <p className={styles.eyebrow}>EDIT</p>
            <h1>{boardTitle} 글 수정</h1>
          </div>

          <Link to={`/boards/${boardType}/${postId}`} className={styles.backButton}>
            상세로
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
            {isLoading ? '수정 중...' : '수정하기'}
          </button>
        </form>
      </section>
    </main>
  )
}

export default BoardEditView
