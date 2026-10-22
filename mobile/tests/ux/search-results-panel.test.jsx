import React, { useState } from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';

const gesture = vi.hoisted(() => ({ handlers: null, motion: null }));
vi.mock('@/constants/theme', () => ({ Palette: {}, Radius: {}, Shadow: {} }));
vi.mock('react-native', () => {
  class Value {
    constructor(value) { this.value = value; this.listeners = new Map(); gesture.motion = this; }
    setValue(value) { this.value = value; this.listeners.forEach(fn => fn({ value })); }
    addListener(fn) { const key = String(this.listeners.size); this.listeners.set(key, fn); return key; }
    removeListener(key) { this.listeners.delete(key); }
    stopAnimation() {}
  }
  const View = ({ children, accessibilityElementsHidden }) => <div aria-hidden={accessibilityElementsHidden}>{children}</div>;
  return {
    View, Text: ({ children }) => <span>{children}</span>,
    Pressable: ({ children, onPress, accessibilityLabel }) => <button aria-label={accessibilityLabel} onClick={onPress}>{children}</button>,
    StyleSheet: { create: value => value },
    Animated: { View, Value, timing: (value, config) => ({ start: () => value.setValue(config.toValue), stop() {} }) },
    PanResponder: { create: handlers => { gesture.handlers = handlers; return { panHandlers: {} }; } },
  };
});
import { SearchResultsPanel } from '../../src/components/search-results-panel';

function Child() { const [count, setCount] = useState(0); return <button onClick={() => setCount(count + 1)}>유지된 상태 {count}</button>; }
function Fixture() {
  const [level, setLevel] = useState('peek');
  return <SearchResultsPanel level={level} onLevelChange={setLevel} availableHeight={1000} expandedHeight={700} title="검색 결과" count={8}><Child /></SearchResultsPanel>;
}
it('줄이기는 기본 높이로 돌아오며 접고 다시 열어도 목록을 새로 만들지 않는다', () => {
  render(<Fixture />);
  fireEvent.click(screen.getByText('유지된 상태 0'));
  fireEvent.click(screen.getByText('목록 확대'));
  fireEvent.click(screen.getByText('줄이기'));
  expect(screen.getByText('지도 넓게')).toBeTruthy();
  fireEvent.click(screen.getByText('지도 넓게'));
  expect(screen.getByText('목록 열기')).toBeTruthy();
  fireEvent.click(screen.getByText('목록 열기'));
  expect(screen.getByText('유지된 상태 1')).toBeTruthy();
});
it('실제 제스처 처리기는 위아래 드래그와 같은 높이로 돌아오는 짧은 드래그를 처리한다', () => {
  render(<Fixture />);
  act(() => { gesture.handlers.onPanResponderGrant(); gesture.handlers.onPanResponderMove(null, { dy: -280 }); gesture.handlers.onPanResponderRelease(null, { dy: -280, vy: 0 }); });
  expect(screen.getByText('줄이기')).toBeTruthy();
  fireEvent.click(screen.getByText('줄이기'));
  act(() => { gesture.handlers.onPanResponderGrant(); gesture.handlers.onPanResponderMove(null, { dy: 8 }); gesture.handlers.onPanResponderRelease(null, { dy: 8, vy: 0 }); });
  expect(gesture.motion.value).toBe(340);
  act(() => { gesture.handlers.onPanResponderGrant(); gesture.handlers.onPanResponderMove(null, { dy: 260 }); gesture.handlers.onPanResponderRelease(null, { dy: 260, vy: 0 }); });
  expect(screen.getByText('목록 열기')).toBeTruthy();
});
