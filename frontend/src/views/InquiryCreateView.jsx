import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { createInquiry } from '@/api/boards'
import { useAuthStore } from '@/stores/auth'

import styles from './InquiryCreateView.module.css'

const getInquiryErrorMessage = (error) => {
  const data = error.response?.data

  if (!data) {
    return '문의 등록에 실패했습니다.'
  }

  if (data.detail) {
    return data.detail
  }

  const firstFieldError = Object.values(data).flat().find(Boolean)

  return firstFieldError || '문의 등록에 실패했습니다.'
}

const InquiryCreateView = () => {
  const navigate = useNavigate()
  const isLoggedIn = useAuthStore((state) => state.isLoggedIn)

  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const validateInquiry = () => {
    if (!title.trim()) {
      return '문의 제목을 입력해주세요.'
    }

    if (content.trim().length < 5) {
      return '문의 내용은 5자 이상 입력해주세요.'
    }

    return ''
  }

  const submitInquiry = async (event) => {
    event.preventDefault()

    if (!isLoggedIn) {
      navigate('/login')
      return
    }

    const validationMessage = validateInquiry()

    if (validationMessage) {
      setErrorMessage(validationMessage)
      return
    }

    try {
      setIsSubmitting(true)
      setErrorMessage('')
      await createInquiry({ title, content })
      navigate('/mypage')
    } catch (error) {
      console.error(error)
      setErrorMessage(getInquiryErrorMessage(error))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className={styles.page}>
      <form className={styles.formCard} onSubmit={submitInquiry}>
        <p className={styles.eyebrow}>INQUIRY</p>
        <h1>문의하기</h1>
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          type="text"
          placeholder="문의 제목"
        />
        <textarea
          value={content}
          onChange={(event) => setContent(event.target.value)}
          rows={8}
          placeholder="문의 내용을 입력하세요"
        />
        {errorMessage ? <p className={styles.error}>{errorMessage}</p> : null}
        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? '등록 중' : '문의 등록'}
        </button>
      </form>
    </main>
  )
}

export default InquiryCreateView
