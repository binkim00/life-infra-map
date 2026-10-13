import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { useAuthStore } from '@/stores/auth'
import styles from './LoginView.module.css'

export default function SocialCallbackView() {
  const navigate = useNavigate()
  const exchange = useAuthStore((state) => state.exchangeSocialTicket)
  const [error, setError] = useState('')
  const started = useRef(false)

  useEffect(() => {
    if (started.current) return
    started.current = true
    const params = new URLSearchParams(window.location.search)
    const ticket = params.get('ticket')
    const nonce = params.get('nonce')
    const expected = sessionStorage.getItem('socialLoginNonce')
    sessionStorage.removeItem('socialLoginNonce')
    window.history.replaceState({}, '', '/oauth/callback')
    if (!expected || nonce !== expected || !ticket || params.has('error')) {
      setError('소셜 로그인을 확인하지 못했습니다. 다시 시도해 주세요.')
      return
    }
    exchange(ticket).then(() => navigate('/', { replace: true }))
      .catch(() => setError('소셜 로그인을 완료하지 못했습니다. 다시 시도해 주세요.'))
  }, [exchange, navigate])

  return <main className={styles.authPage}><section className={styles.authCard}>
    <h1>소셜 로그인</h1>
    <p>{error || '로그인을 완료하고 있습니다.'}</p>
    {error && <Link to="/login" className={styles.authLink}>로그인으로 돌아가기</Link>}
  </section></main>
}
