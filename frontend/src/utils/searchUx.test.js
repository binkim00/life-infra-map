import { describe, it, expect } from 'vitest'
import { conditionChips, placeKey, referencedPlaceKeys, nextBackAction } from '../../../shared/search-ux'
import { userText, userErrorMessage, errorDiagnostic } from '../../../shared/user-message'
describe('shared mobile/web presentation contracts', () => {
 it('only renders canonical fields', () => expect(conditionChips({ place_intent_frame: { anchor_location: '서면', candidate_place_types: ['cafe'], required_features: ['주차', '실내 반려견 동반'], radius_m: 1000 } })).toEqual(['서면', '카페', '주차 · 필수', '실내 반려견 동반 · 필수', '1km 이내']))
 it('provider key remains stable with missing coordinates', () => { const rows = [{id:1,source:'db'}, {id:'kakao:1',source:'kakao',lat:35,lng:129}]; expect(placeKey(rows[0])).not.toBe(placeKey(rows[1])); expect(placeKey(rows[1])).toBe('kakao:1'); expect(referencedPlaceKeys({result_indexes:[1]},rows)).toEqual(['kakao:1']) })
 it.each([['keyboard',{keyboard:true,detail:true}],['detailHistory',{detailHistory:true,detail:true}],['detail',{detail:true,panel:'expanded'}],['peek',{panel:'expanded',canGoBack:true}],['collapsed',{panel:'peek',canGoBack:true}],['history',{canGoBack:true,root:true}],['exit',{root:true}],['home',{}]])('back priority %s',(action,state)=>expect(nextBackAction(state)).toBe(action))
 it.each(['Django exception HTTP 500','요청 실패 (400)','OPENAI_API_KEY 설정 오류','internal_enum','Traceback stack trace','Network Error'])('hides diagnostics %s',text=>expect(userText(text)).toBe('요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.'))
 it.each([401,403,404,409,429,500])('maps status %s without code',status=>expect(userErrorMessage({status})).not.toMatch(/\b[45]\d{2}\b/))
 it('logs only safe metadata',()=>expect(errorDiagnostic({response:{status:500},config:{headers:{Authorization:'secret'}},message:'raw traceback'})).toEqual({status:500,kind:'request_failed'}))
})
