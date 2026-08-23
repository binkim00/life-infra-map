import { beforeEach, describe, expect, it, vi } from 'vitest'

const { post } = vi.hoisted(() => ({ post: vi.fn() }))

vi.mock('@/api/axios', () => ({
  default: { post },
}))

import { aiSearchRecommendations, startNewConversationSession } from './recommendation'

describe('conversation search API', () => {
  beforeEach(() => {
    post.mockReset()
    sessionStorage.clear()
    startNewConversationSession()
  })

  it('creates one anonymous session and reuses its server-side context', async () => {
    post
      .mockResolvedValueOnce({ data: { id: 'session-1', conversation_token: 'secret-1' } })
      .mockResolvedValueOnce({ data: { result_count: 3 } })
      .mockResolvedValueOnce({ data: { result_count: 2 } })

    await aiSearchRecommendations({ query: '서면 작업 카페' })
    await aiSearchRecommendations({ query: '그중 더 조용한 곳' })

    expect(post).toHaveBeenNthCalledWith(1, '/recommendations/conversation-sessions/', {})
    expect(post).toHaveBeenNthCalledWith(
      2,
      '/recommendations/conversation-sessions/session-1/turns/',
      expect.objectContaining({ query: '서면 작업 카페' }),
      { headers: { 'X-Conversation-Token': 'secret-1' } },
    )
    expect(post).toHaveBeenNthCalledWith(
      3,
      '/recommendations/conversation-sessions/session-1/turns/',
      expect.objectContaining({ query: '그중 더 조용한 곳' }),
      { headers: { 'X-Conversation-Token': 'secret-1' } },
    )
  })

  it('recreates a stale session once', async () => {
    sessionStorage.setItem('lifeInfraMap.conversationSession.v1', JSON.stringify({
      id: 'stale-session',
      token: 'stale-token',
    }))
    post
      .mockRejectedValueOnce({ response: { status: 404 } })
      .mockResolvedValueOnce({ data: { id: 'session-2', conversation_token: 'secret-2' } })
      .mockResolvedValueOnce({ data: { result_count: 1 } })

    const result = await aiSearchRecommendations({ query: '다시 찾아줘' })

    expect(result.result_count).toBe(1)
    expect(post).toHaveBeenCalledTimes(3)
  })

  it('clears persisted context when a new conversation starts', () => {
    sessionStorage.setItem('lifeInfraMap.conversationSession.v1', '{"id":"session-1"}')

    startNewConversationSession()

    expect(sessionStorage.getItem('lifeInfraMap.conversationSession.v1')).toBeNull()
  })
})
