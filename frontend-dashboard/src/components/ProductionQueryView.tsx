// src/components/ProductionQueryView.tsx
import React, { useState, useEffect } from 'react';
import { Search, RotateCcw } from 'lucide-react';
import { Card } from './ui/Card';

interface QcTableRecord {
  rowhash: string;
  Marker: string;
  Weekly: string;
  dD生產日: string;
  檢驗日期: string;
  最終判定: string;
  Note: string;
  匹配批號: string;
  初判併批: string;
  限制使用狀態: string;
  限制使用狀態2: string;
  tASTi限用範圍: string;
  source_table?: string;
  [key: string]: string | undefined;
}

const ProductionQueryView: React.FC = () => {
  const [filters, setFilters] = useState({
    marker: '',
    prod_start: '',
    prod_end: '',
    insp_start: '',
    insp_end: '',
    batchable: ''
  });

  const [options, setOptions] = useState<{ makers: string[], batch_options: string[] }>({ makers: [], batch_options: [] });
  const [tableData, setTableData] = useState<QcTableRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [firstLoad, setFirstLoad] = useState(true);

  // 載入選項
  useEffect(() => {
    const fetchOptions = async () => {
      try {
        const res = await fetch(`/api/options`);
        const data = await res.json();
        setOptions(data);
      } catch (err) {
        console.error("無法載入選項", err);
      }
    };
    fetchOptions();
  }, []);

  // 搜尋函式
  const handleSearch = async () => {
    setLoading(true);
    setFirstLoad(false);
    try {
      const params = new URLSearchParams();
      if (filters.marker) params.append('marker', filters.marker);
      if (filters.prod_start) params.append('prod_start', filters.prod_start);
      if (filters.prod_end) params.append('prod_end', filters.prod_end);
      if (filters.insp_start) params.append('insp_start', filters.insp_start);
      if (filters.insp_end) params.append('insp_end', filters.insp_end);
      if (filters.batchable) params.append('batchable', filters.batchable);

      const res = await fetch(`/api/qc_table?${params.toString()}`);
      if (!res.ok) throw new Error('API Error');
      
      const data = await res.json();
      setTableData(data);
    } catch (err) {
      alert("搜尋失敗，請確認後端連線");
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setFilters({
      marker: '',
      prod_start: '',
      prod_end: '',
      insp_start: '',
      insp_end: '',
      batchable: ''
    });
    setTableData([]);
    setFirstLoad(true);
  };

  const columns = [
    { title: 'Marker', key: 'Marker', width: 'w-24' },
    { title: 'Weekly', key: 'Weekly', width: 'w-20' },
    { title: '生產日', key: 'dD生產日', width: 'w-28' },
    { title: '檢驗日', key: '檢驗日期', width: 'w-28' },
    { title: '最終判定', key: '最終判定', width: 'w-24' },
    { title: 'Note', key: 'Note', width: 'w-48' },
    { title: '匹配批號', key: '匹配批號', width: 'w-32' },
    { title: '初判併批', key: '初判併批', width: 'w-24' },
    { title: '限制使用狀態', key: '限制使用狀態', width: 'w-32' },
    { title: '限制使用狀態2', key: '限制使用狀態2', width: 'w-32' },
    { title: 'tASTi限用範圍', key: 'tASTi限用範圍', width: 'w-32' },
  ];

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <Card className="p-6">
        <h3 className="text-xl font-semibold text-slate-200 mb-6 flex items-center gap-2">
          <Search className="text-blue-400" size={24} />
          生管查詢 (Beads IPQC)
        </h3>

        {/* 佈局說明: 
            lg:grid-cols-6 (大螢幕分6欄)
            Marker(1) | Batchable(1) | ProdStart(1) | ProdEnd(1) | InspStart(1) | InspEnd(1)
            Buttons(全寬, 靠右)
        */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-4 mb-6 items-end bg-slate-800/50 p-4 rounded-lg border border-slate-700">
          
          {/* 1. Marker (試劑) */}
          <div className="lg:col-span-1">
            <label className="block text-xs font-medium text-slate-400 mb-1">Marker (試劑)</label>
            <select
              value={filters.marker}
              onChange={e => setFilters({...filters, marker: e.target.value})}
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm focus:ring-2 focus:ring-blue-500 outline-none"
            >
              <option value="">全部</option>
              {options.makers.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>

          {/* 2. 併批狀態 */}
          <div className="lg:col-span-1">
            <label className="block text-xs font-medium text-slate-400 mb-1">併批狀態</label>
            <select
              value={filters.batchable}
              onChange={e => setFilters({...filters, batchable: e.target.value})}
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm focus:ring-2 focus:ring-blue-500 outline-none"
            >
              <option value="">全部</option>
              {options.batch_options.map(b => <option key={b} value={b}>{b}</option>)}
            </select>
          </div>

          {/* 3. 生產日 (起) */}
          <div className="lg:col-span-1">
            <label className="block text-xs font-medium text-slate-400 mb-1">生產日 (起)</label>
            <input 
              type="date" 
              value={filters.prod_start} 
              onChange={e => setFilters({...filters, prod_start: e.target.value})} 
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm focus:ring-2 focus:ring-blue-500 outline-none" 
            />
          </div>

          {/* 4. 生產日 (迄) */}
          <div className="lg:col-span-1">
            <label className="block text-xs font-medium text-slate-400 mb-1">生產日 (迄)</label>
            <input 
              type="date" 
              value={filters.prod_end} 
              onChange={e => setFilters({...filters, prod_end: e.target.value})} 
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm focus:ring-2 focus:ring-blue-500 outline-none" 
            />
          </div>

          {/* 5. 檢驗日 (起) - 與生產日對齊 */}
          <div className="lg:col-span-1">
            <label className="block text-xs font-medium text-slate-400 mb-1">檢驗日 (起)</label>
            <input 
              type="date" 
              value={filters.insp_start} 
              onChange={e => setFilters({...filters, insp_start: e.target.value})} 
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm focus:ring-2 focus:ring-blue-500 outline-none" 
            />
          </div>

          {/* 6. 檢驗日 (迄) - 與生產日對齊 */}
          <div className="lg:col-span-1">
            <label className="block text-xs font-medium text-slate-400 mb-1">檢驗日 (迄)</label>
            <input 
              type="date" 
              value={filters.insp_end} 
              onChange={e => setFilters({...filters, insp_end: e.target.value})} 
              className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm focus:ring-2 focus:ring-blue-500 outline-none" 
            />
          </div>

          {/* 7. 按鈕區 (獨立一列，靠右) */}
          <div className="col-span-1 md:col-span-2 lg:col-span-6 flex justify-end gap-2 mt-2 pt-2 border-t border-slate-700/50">
            <button onClick={handleSearch} disabled={loading} className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition disabled:bg-slate-600 flex items-center justify-center gap-2 text-sm font-medium shadow-lg shadow-blue-900/20">
              {loading ? <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div> : <Search size={16}/>}
              搜尋
            </button>
            <button onClick={handleReset} disabled={loading} className="px-4 py-2 bg-slate-600 hover:bg-slate-500 text-white rounded-lg transition disabled:bg-slate-700 flex items-center justify-center shadow-lg shadow-slate-900/20">
              <RotateCcw size={16} />
            </button>
          </div>
        </div>

        {/* 表格顯示區域 */}
        <div className="overflow-x-auto rounded-lg border border-slate-700 bg-slate-900/30">
          <table className="w-full text-sm text-left text-slate-300">
            <thead className="text-xs text-slate-200 uppercase bg-slate-800 border-b border-slate-700">
              <tr>
                <th className="px-4 py-3 border-r border-slate-700 w-12 text-center">#</th>
                {columns.map((col) => (
                  <th key={col.key} className={`px-4 py-3 border-r border-slate-700 font-bold whitespace-nowrap ${col.width}`}>
                    {col.title}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                 <tr><td colSpan={columns.length + 1} className="px-6 py-12 text-center text-slate-500">資料讀取中...</td></tr>
              ) : tableData.length === 0 ? (
                <tr><td colSpan={columns.length + 1} className="px-6 py-12 text-center text-slate-500">{firstLoad ? "請輸入搜尋條件 (例如日期區間) 並點擊搜尋" : "查無符合條件的資料"}</td></tr>
              ) : (
                tableData.map((row, index) => (
                  <tr key={row.rowhash || index} className="bg-slate-900/50 border-b border-slate-800 hover:bg-slate-800 transition-colors">
                    <td className="px-4 py-3 text-center text-slate-500 border-r border-slate-800">{index + 1}</td>
                    {columns.map((col) => (
                      <td key={col.key} className="px-4 py-3 border-r border-slate-800 whitespace-nowrap truncate max-w-[200px]" title={row[col.key] || ''}>
                        <span className={row[col.key] ? "text-slate-300" : "text-slate-600"}>{row[col.key] || '-'}</span>
                      </td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        
        {tableData.length > 0 && (
          <div className="mt-3 text-xs text-slate-400 text-right">共顯示 {tableData.length} 筆資料</div>
        )}
      </Card>
    </div>
  );
};

export default ProductionQueryView;