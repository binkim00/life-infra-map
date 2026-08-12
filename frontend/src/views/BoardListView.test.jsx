import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import BoardListView from './BoardListView'

const getPosts = vi.fn()

vi.mock('@/api/boards', () => ({
  getPosts: (...args) => getPosts(...args),
}))

const POSTS = [
  {
    id: 1,
    board_type: 'free',
    title: '첫 번째 글',
    author_nickname: '작성자A',
    author_username: 'usera',
    created_at: '2026-08-01T09:00:00Z',
    comments_count: 2,
    likes_count: 5,
    is_pinned: false,
  },
  {
    id: 2,
    board_type: 'free',
    title: '고정된 공지',
    author_nickname: '운영자',
    author_username: 'admin',
    created_at: '2026-07-01T09:00:00Z',
    comments_count: 0,
    likes_count: 1,
    is_pinned: true,
  },
]

const renderBoardList = (boardType = 'free') => render(
  <MemoryRouter initialEntries={[`/boards/${boardType}`]}>
    <Routes>
      <Route path="/boards/:boardType" element={<BoardListView />} />
    </Routes>
  </MemoryRouter>,
)

describe('BoardListView', () => {
  beforeEach(() => {
    // 비로그인 상태입니다.
    localStorage.clear()
    getPosts.mockReset()
    getPosts.mockResolvedValue({ data: POSTS })
  })

  it('로그인하지 않아도 게시글 목록이 보입니다', async () => {
    renderBoardList('free')

    await waitFor(() => {
      expect(screen.getByText('첫 번째 글')).toBeInTheDocument()
    })

    expect(getPosts).toHaveBeenCalledWith('free')
    expect(screen.getByText('고정된 공지')).toBeInTheDocument()
    expect(screen.getByText('총 2개')).toBeInTheDocument()
  })

  it('비로그인이면 자유게시판에 로그인 버튼을 보여줍니다', async () => {
    renderBoardList('free')

    await waitFor(() => {
      expect(screen.getByText('첫 번째 글')).toBeInTheDocument()
    })

    expect(screen.getByRole('link', { name: '로그인' })).toHaveAttribute('href', '/login')
  })

  it('고정 글을 목록 맨 위로 올립니다', async () => {
    renderBoardList('free')

    await waitFor(() => {
      expect(screen.getByText('첫 번째 글')).toBeInTheDocument()
    })

    const titles = screen.getAllByRole('row')
      .slice(1)
      .map((row) => row.textContent)

    expect(titles[0]).toContain('고정된 공지')
  })

  it('목록을 못 받아오면 오류 문구를 보여줍니다', async () => {
    getPosts.mockRejectedValue(new Error('network'))

    renderBoardList('free')

    await waitFor(() => {
      expect(screen.getByText('게시글 목록을 불러오지 못했습니다.')).toBeInTheDocument()
    })
  })
})
