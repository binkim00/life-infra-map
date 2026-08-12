import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { useAuthStore } from '@/stores/auth'

import styles from './SignupView.module.css'

const SignupView = () => {
  const navigate = useNavigate()
  const signup = useAuthStore((state) => state.signup)

  const [username, setUsername] = useState('')
  const [nickname, setNickname] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [passwordConfirm, setPasswordConfirm] = useState('')
  const [profileImageFile, setProfileImageFile] = useState(null)
  const [profileImagePreviewUrl, setProfileImagePreviewUrl] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  // createObjectURL 로 만든 주소는 직접 반납해야 합니다.
  useEffect(() => {
    if (!profileImagePreviewUrl) return undefined

    return () => {
      URL.revokeObjectURL(profileImagePreviewUrl)
    }
  }, [profileImagePreviewUrl])

  const handleProfileImageChange = (event) => {
    const file = event.target.files?.[0]

    setProfileImageFile(file || null)
    setProfileImagePreviewUrl(file ? URL.createObjectURL(file) : '')
  }

  const handleSignup = async (event) => {
    event.preventDefault()
    setErrorMessage('')

    if (!username || !nickname || !password || !passwordConfirm) {
      setErrorMessage('아이디, 닉네임, 비밀번호를 입력해주세요.')
      return
    }

    if (password !== passwordConfirm) {
      setErrorMessage('비밀번호가 일치하지 않습니다.')
      return
    }

    try {
      setIsLoading(true)

      const payload = new FormData()
      payload.append('username', username)
      payload.append('nickname', nickname)
      payload.append('email', email)
      payload.append('password', password)
      payload.append('password_confirm', passwordConfirm)

      if (profileImageFile) {
        payload.append('profile_image', profileImageFile)
      }

      await signup(payload)

      navigate('/')
    } catch (error) {
      console.error(error)
      setErrorMessage('회원가입에 실패했습니다.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <main className={styles.authPage}>
      <section className={styles.authCard}>
        <h1>회원가입</h1>
        <p>생활 장소 추천 서비스를 이용하기 위한 계정을 만들어주세요.</p>

        <form onSubmit={handleSignup} className={styles.authForm}>
          <label className={styles.profileImagePicker}>
            <span className={styles.profileAvatarPreview}>
              {profileImagePreviewUrl ? (
                <img src={profileImagePreviewUrl} alt="프로필 사진 미리보기" />
              ) : (
                <span className={styles.defaultAvatar} aria-hidden="true" />
              )}
            </span>
            <span>프로필 사진 선택</span>
            <input type="file" accept="image/*" onChange={handleProfileImageChange} />
          </label>

          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            type="text"
            placeholder="아이디"
          />
          <input
            value={nickname}
            onChange={(event) => setNickname(event.target.value)}
            type="text"
            placeholder="닉네임"
          />
          <input
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            type="email"
            placeholder="이메일 선택"
          />
          <input
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            type="password"
            placeholder="비밀번호"
          />
          <input
            value={passwordConfirm}
            onChange={(event) => setPasswordConfirm(event.target.value)}
            type="password"
            placeholder="비밀번호 확인"
          />

          {errorMessage ? (
            <p className={styles.errorMessage}>{errorMessage}</p>
          ) : null}

          <button type="submit" disabled={isLoading}>
            {isLoading ? '처리 중...' : '회원가입'}
          </button>
        </form>

        <Link to="/login" className={styles.authLink}>
          이미 계정이 있으신가요? 로그인
        </Link>
      </section>
    </main>
  )
}

export default SignupView
