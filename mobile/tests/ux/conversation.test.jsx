import React, { useEffect } from 'react'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
const mock = vi.hoisted(() => ({ turn: vi.fn(), create: vi.fn(), close: vi.fn(), scroll: vi.fn(), keyboard: false, back: vi.fn(), replace: vi.fn(), canGoBack: false, alert: vi.fn(), exit: vi.fn() }))
vi.mock('react-native', () => {
 const Box = ({children,onLayout}) => { useEffect(()=>{onLayout?.({nativeEvent:{layout:{y:100}}})},[]); return <div>{children}</div> }
 return { View:Box,Text:({children})=><span>{children}</span>,ScrollView:Box,ActivityIndicator:()=>null,
 Pressable:({children,onPress,disabled,accessibilityLabel})=><button disabled={disabled} aria-label={accessibilityLabel} onClick={onPress}>{children}</button>,
 TextInput:({value,onChangeText,accessibilityLabel})=><input aria-label={accessibilityLabel} value={value} onChange={e=>onChangeText(e.target.value)}/>,
 StyleSheet:{create:x=>x},Alert:{alert:(...args)=>{mock.alert(...args);args[2]?.find(x=>x.text==='새로 시작')?.onPress?.()}},Linking:{canOpenURL:async()=>true,openURL:async()=>{}},
 Keyboard:{isVisible:()=>mock.keyboard,dismiss:()=>{mock.keyboard=false}},Platform:{OS:'android'},BackHandler:{exitApp:mock.exit} }
})
vi.mock('expo-router',()=>({useLocalSearchParams:()=>({}),useFocusEffect:fn=>useEffect(fn,[fn]),router:{push:vi.fn(),canGoBack:()=>mock.canGoBack,back:mock.back,replace:mock.replace}}))
vi.mock('@/utils/location',()=>({searchLocation:async()=>null}))
vi.mock('@/auth/auth-context',()=>({useAuth:()=>({isLoggedIn:false,requireLogin:()=>false})}))
vi.mock('@/api/client',()=>({ApiError:class extends Error{}}))
vi.mock('@/api/recommendations',()=>({recommendationApi:{createConversationSession:mock.create,sendConversationTurn:mock.turn,closeConversationSession:mock.close}}))
vi.mock('@/components/screen',()=>({Screen:({children,footer,scrollRef})=>{useEffect(()=>{scrollRef.current={scrollTo:mock.scroll}},[]);return <main>{children}<footer>{footer}</footer></main>},ui:{},INPUT_PLACEHOLDER_COLOR:'#aaa'}))
vi.mock('@/components/place-map',()=>({PlaceMap:({places,onSelectPlace,place})=><div data-testid="map" data-selected={place?.id}>{places.map(item=><button key={item.id} onClick={()=>onSelectPlace(item)}>마커 {item.name}</button>)}</div>}))
vi.mock('@/components/place-detail-sheet',()=>({PlaceDetailSheet:({visible,onClose,place})=>visible?<section><span>{place.name} 상세</span><button onClick={onClose}>상세 닫기</button></section>:null}))
import RecommendScreen from '../../src/app/(tabs)/recommend'
import { handleAppBack, registerBackHandler } from '../../src/utils/back-navigation'
const plan={place_intent_frame:{anchor_location:'서면',candidate_place_types:['카페'],required_features:['주차'],radius_m:1000}}
const rows=[{id:'db:1',name:'첫 카페',category:'cafe',lat:35,lng:129},{id:'db:2',name:'두 번째 카페',category:'cafe',lat:35.1,lng:129.1}]
const response={decision_action:'search',results:rows,search_plan:plan}
const send=async(user,text)=>{await user.type(screen.getByLabelText('상황 검색 메시지'),text);await user.click(screen.getByRole('button',{name:'보내기'}))}
const ready=async()=>{render(<RecommendScreen/>);await waitFor(()=>expect(mock.create).toHaveBeenCalledTimes(1));await act(async()=>{});return userEvent.setup()}
describe('mobile conversation UX with native adapters',()=>{
 beforeEach(()=>{vi.clearAllMocks();mock.create.mockResolvedValue({id:'session',conversation_token:'token'});mock.close.mockResolvedValue({});mock.turn.mockReset();mock.keyboard=false;mock.canGoBack=false})
 it('검색 → 상세 → 닫기 뒤 결과와 조건이 유지됩니다',async()=>{mock.turn.mockResolvedValue(response);const user=await ready();await send(user,'서면 카페');await screen.findByRole('button',{name:'마커 첫 카페'});await user.click(screen.getAllByRole('button',{name:'첫 카페 상세정보'})[0]);await user.click(screen.getByRole('button',{name:'상세 닫기'}));expect(screen.getByRole('button',{name:'마커 두 번째 카페'})).toBeTruthy();expect(screen.getByText('주차 · 필수')).toBeTruthy()})
 it('clarification 선택의 구조화 action과 기존 상태가 보존됩니다',async()=>{const action={type:'relax_constraints',condition_labels:['주차']};mock.turn.mockResolvedValueOnce(response).mockResolvedValueOnce({decision_action:'ask_clarification',message:'범위를 좁힐까요?',clarification_options:[{label:'1km 선택',value:'1km',action}],search_plan:plan}).mockResolvedValueOnce(response);const user=await ready();await send(user,'서면 카페');await screen.findByRole('button',{name:'마커 첫 카페'});await send(user,'범위를 바꿔줘');await user.click(await screen.findByRole('button',{name:'1km 선택'}));await waitFor(()=>expect(mock.turn).toHaveBeenCalledTimes(3));expect(mock.turn.mock.calls[2][2].conversation_action).toEqual(action);expect(screen.getByRole('button',{name:'마커 두 번째 카페'})).toBeTruthy();expect(screen.getByText('주차 · 필수')).toBeTruthy()})
 it('마커 선택은 카드로 스크롤하고 선택 key를 지도에 보냅니다',async()=>{mock.turn.mockResolvedValue(response);const user=await ready();await send(user,'서면 카페');await user.click(await screen.findByRole('button',{name:'마커 두 번째 카페'}));expect(screen.getByTestId('map').dataset.selected).toBe('db:2');await waitFor(()=>expect(mock.scroll).toHaveBeenCalled());await user.click(screen.getAllByRole('button',{name:'첫 카페 상세정보'})[0]);expect(screen.getByTestId('map').dataset.selected).toBe('db:1')})
 it('오류 시 검색어·세션·조건·결과를 유지하고 같은 요청을 재시도합니다',async()=>{mock.turn.mockResolvedValueOnce(response).mockRejectedValueOnce(new Error('HTTP 500 Django exception')).mockResolvedValueOnce(response);const user=await ready();await send(user,'서면 카페');await screen.findByRole('button',{name:'마커 첫 카페'});await send(user,'주차 확인');await screen.findByRole('button',{name:'같은 조건으로 다시 시도'});expect(screen.getByLabelText('상황 검색 메시지').value).toBe('주차 확인');expect(screen.queryByText(/Django exception/)).toBeNull();await user.click(screen.getByRole('button',{name:'같은 조건으로 다시 시도'}));await waitFor(()=>expect(mock.turn).toHaveBeenCalledTimes(3));expect(mock.turn.mock.calls[1]).toEqual(mock.turn.mock.calls[2]);expect(mock.create).toHaveBeenCalledTimes(1)})
 it('새 대화 후 늦은 응답과 중복 탭이 새 화면을 바꾸지 않습니다',async()=>{let resolve;mock.turn.mockReturnValue(new Promise(r=>resolve=r));const user=await ready();await send(user,'서면 카페');await waitFor(()=>expect(mock.turn).toHaveBeenCalledTimes(1));await user.click(screen.getByRole('button',{name:'＋ 새 대화'}));await act(async()=>resolve(response));expect(screen.queryByRole('button',{name:'마커 첫 카페'})).toBeNull();expect(screen.queryByText('주차 · 필수')).toBeNull();expect(mock.create).toHaveBeenCalledTimes(2)})
 it('뒤로 가기는 키보드 → 화면 처리 → history → 홈 → 실제 루트 종료 순서입니다',()=>{let overlay=true;const unregister=registerBackHandler(()=>{if(!overlay)return false;overlay=false;return true});mock.keyboard=true;handleAppBack('/explore');expect(overlay).toBe(true);handleAppBack('/explore');expect(overlay).toBe(false);unregister();mock.canGoBack=true;handleAppBack('/');expect(mock.back).toHaveBeenCalledOnce();mock.canGoBack=false;handleAppBack('/explore');expect(mock.replace).toHaveBeenCalledWith('/');expect(mock.alert).not.toHaveBeenCalled();handleAppBack('/');expect(mock.alert).toHaveBeenCalledWith('앱 종료',expect.any(String),expect.any(Array),expect.any(Object))})
})
