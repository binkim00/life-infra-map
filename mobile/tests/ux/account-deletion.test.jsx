import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import AccountDeletionScreen from '../../src/app/account-deletion'
const mock=vi.hoisted(()=>({read:vi.fn(),request:vi.fn(),clear:vi.fn(),replace:vi.fn(),confirm:null}))
vi.mock('react-native',()=>({View:({children})=><div>{children}</div>,Text:({children})=><span>{children}</span>,TextInput:({value,onChangeText,accessibilityLabel})=><input aria-label={accessibilityLabel} value={value} onChange={e=>onChangeText(e.target.value)}/>,Pressable:({children,onPress,disabled})=><button disabled={disabled} onClick={onPress}>{children}</button>,StyleSheet:{create:x=>x},Alert:{alert:(_title,_body,buttons)=>{mock.confirm=buttons.find(b=>b.style==='destructive').onPress}}}))
vi.mock('expo-router',()=>({router:{replace:mock.replace}}))
vi.mock('@/api/client',()=>({apiRequest:mock.request,authStorage:{read:mock.read,clear:mock.clear}}))
vi.mock('@/auth/auth-context',()=>({useAuth:()=>({user:{username:'qa'},isLoggedIn:true})}))
vi.mock('@/components/screen',()=>({Screen:({children})=><main>{children}</main>,ui:{}}))
beforeEach(()=>{vi.clearAllMocks();mock.confirm=null;mock.request.mockReset();mock.clear.mockResolvedValue();mock.read.mockReset();mock.read.mockResolvedValue({user:{id:1,username:"qa"}})})
const enter=async()=>{render(<AccountDeletionScreen/>);const user=userEvent.setup();await user.type(screen.getByLabelText('삭제할 계정 아이디'),'qa');await user.type(screen.getByLabelText('계정 삭제 확인 문구'),'계정 삭제');await user.click(screen.getByRole('button',{name:'계정 삭제하기'}));return user}
it('확인 전 요청하지 않고 잘못된 아이디와 확인 문구를 차단합니다',async()=>{render(<AccountDeletionScreen/>);await userEvent.click(screen.getByRole('button',{name:'계정 삭제하기'}));expect(mock.request).not.toHaveBeenCalled();mock.confirm();await screen.findByText(/정확히 입력/);expect(mock.request).not.toHaveBeenCalled()})
it('서버 실패 시 인증을 보존하고 성공 후에만 세션을 비우고 홈으로 이동합니다',async()=>{mock.request.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({});await enter();expect(mock.request).not.toHaveBeenCalled();mock.confirm();await screen.findByText(/삭제하지 못했습니다/);expect(mock.clear).not.toHaveBeenCalled();await userEvent.click(screen.getByRole('button',{name:'계정 삭제하기'}));mock.confirm();await waitFor(()=>expect(mock.clear).toHaveBeenCalledOnce());expect(mock.request).toHaveBeenLastCalledWith('/account-deletion/',{method:'POST',body:{username:'qa',confirmation:'계정 삭제'}});expect(mock.replace).toHaveBeenCalledWith('/')})

it('삭제 응답 전에 계정이 전환되면 새 계정의 세션을 지우지 않습니다',async()=>{mock.read.mockResolvedValueOnce({user:{id:1,username:'qa'}}).mockResolvedValueOnce({user:{id:2,username:'other'}});mock.request.mockResolvedValue({});await enter();mock.confirm();await waitFor(()=>expect(mock.read).toHaveBeenCalledTimes(2));expect(mock.clear).not.toHaveBeenCalled();expect(mock.replace).not.toHaveBeenCalled()})

it('삭제 요청 처리 중 확인을 반복해도 요청과 인증 정리는 한 번만 실행됩니다',async()=>{
 let finish;mock.request.mockImplementation(()=>new Promise(resolve=>{finish=resolve}));
 await enter();const confirm=mock.confirm;confirm();confirm();
 await waitFor(()=>expect(mock.request).toHaveBeenCalledOnce());
 expect(mock.read).toHaveBeenCalledTimes(1);expect(mock.clear).not.toHaveBeenCalled();
 finish({});await waitFor(()=>expect(mock.clear).toHaveBeenCalledOnce());
 expect(mock.request).toHaveBeenCalledOnce();expect(mock.replace).toHaveBeenCalledOnce();
})
it('확인창 뒤 요청 직전에 계정이 바뀌면 삭제 요청을 보내지 않습니다',async()=>{
 mock.read.mockResolvedValue({user:{id:2,username:'other'}});
 await enter();mock.confirm();await screen.findByText(/삭제하지 못했습니다/);
 expect(mock.request).not.toHaveBeenCalled();expect(mock.clear).not.toHaveBeenCalled();expect(mock.replace).not.toHaveBeenCalled();
})
