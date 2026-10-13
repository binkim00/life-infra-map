import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/auth'
import { useSettingsStore } from '@/stores/settings'
import { useNotifications } from './useNotifications'
const api=vi.hoisted(()=>({get:vi.fn(),all:vi.fn().mockResolvedValue({}),one:vi.fn().mockResolvedValue({})}))
vi.mock('@/api/boards',()=>({getNotifications:api.get,markAllNotificationsRead:api.all,markNotificationRead:api.one}))
const login=id=>act(()=>useAuthStore.setState({isLoggedIn:Boolean(id),user:id?{id}:null,fetchMe:vi.fn()}))
describe('web unread notification lifecycle',()=>{
 beforeEach(()=>{api.get.mockReset();api.get.mockResolvedValue({data:[]});useSettingsStore.setState({commentNotifications:true,inquiryNotifications:true});login(1)})
 it('zero → unread → all read → logout/login',async()=>{const {result}=renderHook(useNotifications);await waitFor(()=>expect(api.get).toHaveBeenCalled());expect(result.current.unreadNotificationCount).toBe(0);api.get.mockResolvedValue({data:[{id:1,is_read:false}]});await act(()=>result.current.fetchNotifications());expect(result.current.unreadNotificationCount).toBe(1);await act(()=>result.current.markAllVisibleNotificationsAsRead());expect(result.current.unreadNotificationCount).toBe(0);login(null);expect(result.current.unreadNotificationCount).toBe(0);login(1);await waitFor(()=>expect(result.current.unreadNotificationCount).toBe(1))})
 it('account switch rejects a late response from the previous account',async()=>{let old;api.get.mockReturnValueOnce(new Promise(r=>old=r));const {result}=renderHook(useNotifications);api.get.mockResolvedValue({data:[]});login(2);await waitFor(()=>expect(api.get).toHaveBeenCalledTimes(2));await act(()=>old({data:[{id:1,is_read:false}]}));expect(result.current.unreadNotificationCount).toBe(0);expect(result.current.visibleNotifications).toEqual([])})
 it('notification settings update the dot from visible unread state',async()=>{api.get.mockResolvedValue({data:[{id:1,is_read:false,notification_type:'post_commented'}]});const {result}=renderHook(useNotifications);await waitFor(()=>expect(result.current.unreadNotificationCount).toBe(1));act(()=>useSettingsStore.getState().setSetting('commentNotifications',false));expect(result.current.unreadNotificationCount).toBe(0);act(()=>useSettingsStore.getState().setSetting('commentNotifications',true));expect(result.current.unreadNotificationCount).toBe(1)})
})
