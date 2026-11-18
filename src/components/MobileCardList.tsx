import React, { useMemo, useState } from 'react';
import { Empty, Pagination, Spin } from 'antd';

interface MobileCardListProps<T> {
  items: T[];
  rowKey: (item: T) => string | number;
  renderCard: (item: T) => React.ReactNode;
  loading?: boolean;
  emptyText?: string;
  /** 客户端分页大小，默认 20；不传则不分页（数据量小时用） */
  pageSize?: number;
  /** 服务端分页：传了 total/page/onPageChange 时走服务端分页 */
  serverSide?: boolean;
  total?: number;
  page?: number;
  onPageChange?: (page: number, pageSize: number) => void;
}

/**
 * 移动端通用卡片列表（B 档适配用）
 * 桌面端仍然走 Table，这个组件只在 isMobile 时渲染。
 */
function MobileCardList<T>({
  items,
  rowKey,
  renderCard,
  loading,
  emptyText = '暂无数据',
  pageSize = 20,
  serverSide,
  total,
  page,
  onPageChange,
}: MobileCardListProps<T>) {
  const [innerPage, setInnerPage] = useState(1);

  const currentPage = serverSide ? page || 1 : innerPage;
  const totalCount = serverSide ? total || 0 : items.length;

  const pageItems = useMemo(() => {
    if (serverSide) return items;
    const start = (innerPage - 1) * pageSize;
    return items.slice(start, start + pageSize);
  }, [items, innerPage, pageSize, serverSide]);

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 40 }}>
        <Spin />
      </div>
    );
  }

  if (items.length === 0) {
    return <Empty description={emptyText} style={{ padding: 32 }} />;
  }

  return (
    <div>
      {pageItems.map((item) => (
        <div key={rowKey(item)} className="m-card">
          {renderCard(item)}
        </div>
      ))}
      {totalCount > pageSize && (
        <Pagination
          style={{ textAlign: 'center', marginTop: 12 }}
          simple
          current={currentPage}
          pageSize={pageSize}
          total={totalCount}
          onChange={(p, ps) => {
            if (serverSide) onPageChange?.(p, ps);
            else setInnerPage(p);
          }}
        />
      )}
    </div>
  );
}

export default MobileCardList;
