import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { useAuthStore } from '@/stores/auth'

import styles from './LoginView.module.css'

const LoginView = () => {
  const navigate = useNavigate()
  const login = useAuthStore((state) => state.login)

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [penaltyInfo, setPenaltyInfo] = useState(null)
  const [isLoading, setIsLoading] = useState(false)

  const handleLogin = async (event) => {
    event.preventDefault()
    setErrorMessage('')
    setPenaltyInfo(null)

    if (!username || !password) {
      setErrorMessage('아이디와 비밀번호를 입력해주세요.')
      return
    }

    try {
      setIsLoading(true)

      await login({ username, password })

      navigate('/')
    } catch (error) {
      console.error(error)
      if (error.response?.data?.penalty) {
        setErrorMessage(error.response.data.detail)
        setPenaltyInfo(error.response.data.penalty)
      } else {
        setErrorMessage('아이디 또는 비밀번호가 올바르지 않습니다.')
      }
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <main className={styles.authPage}>
      <section className={styles.authCard}>
        <h1>로그인</h1>
        <p>저장한 장소와 개인화 추천 기능을 이용할 수 있습니다.</p>

        <form onSubmit={handleLogin} className={styles.authForm}>
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            type="text"
            placeholder="아이디"
          />
          <input
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            type="password"
            placeholder="비밀번호"
          />

          {errorMessage ? (
            <p className={styles.errorMessage}>{errorMessage}</p>
          ) : null}

          {penaltyInfo ? (
            <div className={styles.penaltyBox}>
              <strong>
                {penaltyInfo.is_permanent_ban
                  ? '현재 계정은 영구밴 상태입니다.'
                  : '현재 계정은 활동정지 상태입니다.'}
              </strong>
              {penaltyInfo.reason ? <p>사유: {penaltyInfo.reason}</p> : null}
              {penaltyInfo.message ? <p>관리자 메시지: {penaltyInfo.message}</p> : null}
              {penaltyInfo.end_at ? (
                <p>정지 해제일: {new Date(penaltyInfo.end_at).toLocaleString()}</p>
              ) : null}
            </div>
          ) : null}

          <button type="submit" disabled={isLoading}>
            {isLoading ? '로그인 중...' : '로그인'}
          </button>
        </form>

        <Link to="/signup" className={styles.authLink}>
          계정이 없으신가요? 회원가입
        </Link>
      </section>
    </main>
  )
}

export default LoginView
