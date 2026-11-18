import { useEffect, useState } from 'react';

/** 移动端断点：与 antd 的 md（768px）对齐，小于该值走移动形态 */
export const MOBILE_BREAKPOINT = 768;

const getIsMobile = () => {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  return window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`).matches;
};

/**
 * 是否处于移动端视口。
 * 用 matchMedia 监听，旋转屏幕 / 拖拽窗口时自动更新，无需刷新。
 */
export function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState(getIsMobile);

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mql = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`);
    const onChange = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    setIsMobile(mql.matches);
    if (mql.addEventListener) {
      mql.addEventListener('change', onChange);
      return () => mql.removeEventListener('change', onChange);
    }
    // 兼容旧版 Safari
    mql.addListener(onChange);
    return () => mql.removeListener(onChange);
  }, []);

  return isMobile;
}

export default useIsMobile;
