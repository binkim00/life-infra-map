import { useEffect } from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
const mock=vi.hoisted(()=>({auth:{ready:true,isLoggedIn:true,user:{id:1}},get:vi.fn(),settings:vi.fn()}))
vi.mock('@/auth/auth-context',()=>({useAuth:()=>mock.auth}))
vi.mock('@/api/boards',()=>({boardsApi:{notifications:mock.get}}))
vi.mock('@react-native-async-storage/async-storage',()=>({default:{getItem:mock.settings}}))
vi.mock('expo-router',()=>({useFocusEffect:fn=>useEffect(fn,[fn])}))
import { useNotifications } from '../../src/hooks/use-notifications'
describe('mobile unread lifecycle with focus adapter',()=>{
 beforeEach(()=>{mock.auth={ready:true,isLoggedIn:true,user:{id:1}};mock.get.mockReset();mock.get.mockResolvedValue([]);mock.settings.mockResolvedValue('{}')})
 it('zero → unread → all read → logout/login',async()=>{const {result,rerender}=renderHook(useNotifications);await waitFor(()=>expect(result.current.loading).toBe(false));expect(result.current.unreadCount).toBe(0);mock.get.mockResolvedValue([{id:1,is_read:false}]);await act(()=>result.current.reload());expect(result.current.unreadCount).toBe(1);mock.get.mockResolvedValue([{id:1,is_read:true}]);await act(()=>result.current.reload());expect(result.current.unreadCount).toBe(0);mock.auth={...mock.auth,isLoggedIn:false};rerender();expect(result.current.unreadCount).toBe(0);mock.get.mockResolvedValue([{id:2,is_read:false}]);mock.auth={...mock.auth,isLoggedIn:true};rerender();await waitFor(()=>expect(result.current.unreadCount).toBe(1))})
 it('account switch rejects an old response',async()=>{let old;mock.get.mockReturnValueOnce(new Promise(r=>old=r));const {result,rerender}=renderHook(useNotifications);mock.get.mockResolvedValue([]);mock.auth={...mock.auth,user:{id:2}};rerender();await act(()=>old([{id:1,is_read:false}]));await waitFor(()=>expect(result.current.loading).toBe(false));expect(result.current.unreadCount).toBe(0)})
 it('focus/reload reads notification settings',async()=>{mock.get.mockResolvedValue([{id:1,is_read:false,notification_type:'post_commented'}]);const {result}=renderHook(useNotifications);await waitFor(()=>expect(result.current.unreadCount).toBe(1));mock.settings.mockResolvedValue('{"commentNotifications":false}');await act(()=>result.current.reload());expect(result.current.unreadCount).toBe(0)})
})
