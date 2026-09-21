'use client';

/**
 * ImageAnalysisTab - QubitClient VLM 图像分析组件
 *
 * 提供量子实验图像的 AI 分析能力：
 * - Q1: describe_plot - 描述图表
 * - Q2: classify_outcome - 分类结果
 * - Q3: scientific_reasoning - 科学推理
 * - Q4: assess_fit - 评估拟合
 * - Q5: extract_params - 提取参数
 * - Q6: evaluate_status - 评估状态
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '@/lib/api';
import type {
  ExperimentFamily,
  FullAnalysisResult,
  HealthResponse,
  DescribePlotResult,
  ClassifyOutcomeResult,
  AssessFitResult,
  EvaluateStatusResult
} from '@/types/qubit';

interface AnalysisResult {
  q1_describe?: DescribePlotResult | string;
  q2_classify?: ClassifyOutcomeResult | string;
  q3_reasoning?: string;
  q4_assess_fit?: AssessFitResult | string;
  q5_extract_params?: Record<string, any> | string;
  q6_evaluate?: EvaluateStatusResult | string;
}

export default function ImageAnalysisTab() {
  // 状态
  const [image, setImage] = useState<string | null>(null); // base64
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [families, setFamilies] = useState<ExperimentFamily[]>([]);
  const [selectedFamily, setSelectedFamily] = useState<string>('drag');
  const [language, setLanguage] = useState<'en' | 'zh'>('zh');
  const [isLoading, setIsLoading] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [results, setResults] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'single' | 'full'>('full');

  const fileInputRef = useRef<HTMLInputElement>(null);

  // 加载初始化数据
  useEffect(() => {
    loadFamilies();
    checkHealth();
  }, []);

  // 加载实验类型列表
  const loadFamilies = async () => {
    try {
      const data = await api.qubitGetFamilies();
      if (data.families) {
        setFamilies(data.families);
      }
    } catch (e) {
      console.error('Failed to load families:', e);
    }
  };

  // 检查健康状态
  const checkHealth = async () => {
    try {
      const data = await api.qubitHealth();
      setHealth(data);
    } catch (e) {
      setHealth({
        status: 'degraded',
        service: 'qubitclient_service',
        initialized: false,
        model: 'N/A',
        base_url: 'N/A',
        error: String(e)
      });
    }
  };

  // 压缩图像到合理大小
  const compressImage = useCallback((file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        // 最大边长 1024 像素
        const maxSize = 1024;
        let { width, height } = img;

        if (width > maxSize || height > maxSize) {
          if (width > height) {
            height = Math.round(height * maxSize / width);
            width = maxSize;
          } else {
            width = Math.round(width * maxSize / height);
            height = maxSize;
          }
        }

        // 创建 canvas 绘制压缩后的图像
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        if (!ctx) {
          reject(new Error('Failed to get canvas context'));
          return;
        }
        ctx.drawImage(img, 0, 0, width, height);

        // 转换为 base64 (JPEG 格式，压缩质量 0.8)
        const compressed = canvas.toDataURL('image/jpeg', 0.8);
        resolve(compressed);
      };
      img.onerror = () => reject(new Error('Failed to load image'));
      img.src = URL.createObjectURL(file);
    });
  }, []);

  // 处理文件上传（带压缩）
  const processFile = useCallback(async (file: File) => {
    try {
      const compressed = await compressImage(file);
      setImage(compressed);
      setImagePreview(compressed);
      setResults(null);
      setError(null);
    } catch (e) {
      // 如果压缩失败，使用原图
      console.error('Image compression failed:', e);
      const reader = new FileReader();
      reader.onload = (event) => {
        const base64 = event.target?.result as string;
        setImage(base64);
        setImagePreview(base64);
        setResults(null);
        setError(null);
      };
      reader.readAsDataURL(file);
    }
  }, [compressImage]);

  // 处理文件选择
  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    processFile(file);
  }, [processFile]);

  // 拖拽上传
  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (!file || !file.type.startsWith('image/')) return;
    processFile(file);
  }, [processFile]);

  // 拖拽事件处理
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
  }, []);

  // 清除图像
  const clearImage = useCallback(() => {
    setImage(null);
    setImagePreview(null);
    setResults(null);
    setError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, []);

  // 执行单任务分析
  const analyzeSingle = async (task: 'q1' | 'q2' | 'q3' | 'q4' | 'q5' | 'q6') => {
    if (!image) {
      setError('请先上传图像');
      return;
    }

    setIsAnalyzing(true);
    setError(null);

    try {
      let result: any;
      switch (task) {
        case 'q1':
          result = await api.qubitDescribe({ image, experiment_family: selectedFamily, language });
          if (result.success) setResults(prev => ({ ...prev, q1_describe: result.result }));
          else setError(result.error);
          break;
        case 'q2':
          result = await api.qubitClassify({ image, experiment_family: selectedFamily, language });
          if (result.success) setResults(prev => ({ ...prev, q2_classify: result.result }));
          else setError(result.error);
          break;
        case 'q3':
          result = await api.qubitReasoning({ image, experiment_family: selectedFamily, language });
          if (result.success) setResults(prev => ({ ...prev, q3_reasoning: result.result }));
          else setError(result.error);
          break;
        case 'q4':
          result = await api.qubitAssessFit({ image, experiment_family: selectedFamily, language });
          if (result.success) setResults(prev => ({ ...prev, q4_assess_fit: result.result }));
          else setError(result.error);
          break;
        case 'q5':
          result = await api.qubitExtractParams({ image, experiment_family: selectedFamily, language });
          if (result.success) setResults(prev => ({ ...prev, q5_extract_params: result.result }));
          else setError(result.error);
          break;
        case 'q6':
          result = await api.qubitEvaluate({ image, experiment_family: selectedFamily, language });
          if (result.success) setResults(prev => ({ ...prev, q6_evaluate: result.result }));
          else setError(result.error);
          break;
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setIsAnalyzing(false);
    }
  };

  // 执行完整分析
  const analyzeFull = async () => {
    if (!image) {
      setError('请先上传图像');
      return;
    }

    setIsAnalyzing(true);
    setError(null);

    try {
      const result = await api.qubitAnalyzeFull({
        image,
        experiment_family: selectedFamily,
        language
      });

      if (result.success && result.results) {
        setResults({
          q1_describe: result.results.describe_plot,
          q2_classify: result.results.classify_outcome,
          q3_reasoning: result.results.scientific_reasoning,
          q4_assess_fit: result.results.assess_fit,
          q5_extract_params: result.results.extract_params,
          q6_evaluate: result.results.evaluate_status,
        });
      } else {
        setError(result.error || '分析失败');
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setIsAnalyzing(false);
    }
  };

  // 渲染结果卡片
  const renderResultCard = (title: string, task: keyof AnalysisResult, content: any) => {
    if (!content) return null;

    return (
      <div style={styles.resultCard}>
        <div style={styles.resultHeader}>{title}</div>
        <div style={styles.resultContent}>
          {typeof content === 'string' ? (
            <pre style={styles.resultText}>{content}</pre>
          ) : (
            <pre style={styles.resultJson}>{JSON.stringify(content, null, 2)}</pre>
          )}
        </div>
      </div>
    );
  };

  return (
    <div style={styles.container}>
      {/* 头部信息 */}
      <div style={styles.header}>
        <div style={styles.title}>
          <span style={styles.icon}>🔬</span>
          <span>图像分析</span>
          <span style={styles.modelTag}>{health?.model || 'Loading...'}</span>
        </div>
        <div style={styles.status}>
          <span style={{
            ...styles.statusDot,
            background: health?.status === 'healthy' ? '#22c55e' : '#ef4444'
          }} />
          <span style={styles.statusText}>
            {health?.status === 'healthy' ? '已连接' : '未连接'}
          </span>
          <button onClick={checkHealth} style={styles.refreshBtn}>刷新</button>
        </div>
      </div>

      {/* 主内容区 */}
      <div style={styles.main}>
        {/* 左侧：图像上传 */}
        <div style={styles.leftPanel}>
          <div
            style={{
              ...styles.dropZone,
              ...(imagePreview ? styles.dropZoneActive : {}),
            }}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onClick={() => fileInputRef.current?.click()}
          >
            {imagePreview ? (
              <img src={imagePreview} alt="Preview" style={styles.previewImage} />
            ) : (
              <div style={styles.dropZoneText}>
                <div style={styles.dropIcon}>📁</div>
                <div>拖拽图像到这里</div>
                <div style={styles.dropSubtext}>或点击选择文件</div>
              </div>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={handleFileSelect}
              style={{ display: 'none' }}
            />
          </div>

          {image && (
            <button onClick={clearImage} style={styles.clearBtn}>
              清除图像
            </button>
          )}

          {/* 选项 */}
          <div style={styles.options}>
            <div style={styles.optionGroup}>
              <label style={styles.label}>实验类型</label>
              <select
                value={selectedFamily}
                onChange={(e) => setSelectedFamily(e.target.value)}
                style={styles.select}
              >
                {families.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name} - {f.description}
                  </option>
                ))}
              </select>
            </div>

            <div style={styles.optionGroup}>
              <label style={styles.label}>语言</label>
              <div style={styles.radioGroup}>
                <label style={styles.radioLabel}>
                  <input
                    type="radio"
                    value="zh"
                    checked={language === 'zh'}
                    onChange={() => setLanguage('zh')}
                  />
                  中文
                </label>
                <label style={styles.radioLabel}>
                  <input
                    type="radio"
                    value="en"
                    checked={language === 'en'}
                    onChange={() => setLanguage('en')}
                  />
                  English
                </label>
              </div>
            </div>
          </div>
        </div>

        {/* 右侧：结果 */}
        <div style={styles.rightPanel}>
          {/* 分析模式切换 */}
          <div style={styles.tabs}>
            <button
              style={{ ...styles.tab, ...(activeTab === 'full' ? styles.tabActive : {}) }}
              onClick={() => setActiveTab('full')}
            >
              完整分析
            </button>
            <button
              style={{ ...styles.tab, ...(activeTab === 'single' ? styles.tabActive : {}) }}
              onClick={() => setActiveTab('single')}
            >
              单步分析
            </button>
          </div>

          {/* 错误提示 */}
          {error && (
            <div style={styles.error}>
              <span>❌</span> {error}
            </div>
          )}

          {/* 分析按钮 */}
          {activeTab === 'full' && (
            <button
              onClick={analyzeFull}
              disabled={!image || isAnalyzing}
              style={{
                ...styles.analyzeBtn,
                ...(image && !isAnalyzing ? {} : styles.analyzeBtnDisabled),
              }}
            >
              {isAnalyzing ? '分析中...' : '🔍 完整分析 (Q1-Q6)'}
            </button>
          )}

          {activeTab === 'single' && (
            <div style={styles.singleButtons}>
              <button onClick={() => analyzeSingle('q1')} disabled={!image || isAnalyzing} style={styles.taskBtn}>
                Q1 描述
              </button>
              <button onClick={() => analyzeSingle('q2')} disabled={!image || isAnalyzing} style={styles.taskBtn}>
                Q2 分类
              </button>
              <button onClick={() => analyzeSingle('q3')} disabled={!image || isAnalyzing} style={styles.taskBtn}>
                Q3 推理
              </button>
              <button onClick={() => analyzeSingle('q4')} disabled={!image || isAnalyzing} style={styles.taskBtn}>
                Q4 评估
              </button>
              <button onClick={() => analyzeSingle('q5')} disabled={!image || isAnalyzing} style={styles.taskBtn}>
                Q5 参数
              </button>
              <button onClick={() => analyzeSingle('q6')} disabled={!image || isAnalyzing} style={styles.taskBtn}>
                Q6 状态
              </button>
            </div>
          )}

          {/* 加载状态 */}
          {isAnalyzing && (
            <div style={styles.loading}>
              <div style={styles.spinner} />
              <span>正在分析图像...</span>
            </div>
          )}

          {/* 结果展示 */}
          {results && (
            <div style={styles.results}>
              <div style={styles.resultsTitle}>分析结果</div>

              {renderResultCard('Q1 图表描述', 'q1_describe', results.q1_describe)}
              {renderResultCard('Q2 结果分类', 'q2_classify', results.q2_classify)}
              {renderResultCard('Q3 科学推理', 'q3_reasoning', results.q3_reasoning)}
              {renderResultCard('Q4 拟合评估', 'q4_assess_fit', results.q4_assess_fit)}
              {renderResultCard('Q5 参数提取', 'q5_extract_params', results.q5_extract_params)}
              {renderResultCard('Q6 状态评估', 'q6_evaluate', results.q6_evaluate)}
            </div>
          )}

          {/* 空状态 */}
          {!image && !results && (
            <div style={styles.emptyState}>
              <div style={styles.emptyIcon}>📊</div>
              <div>上传图像开始分析</div>
              <div style={styles.emptySubtext}>
                支持 DRAG、Rabi、Ramsey、T1 等 30+ 种量子实验图像分析
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// 样式
const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: 'calc(100vh - 180px)',
    background: '#0f172a',
    color: '#e2e8f0',
    fontSize: '13px',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '12px 16px',
    background: '#1e293b',
    borderBottom: '1px solid #334155',
  },
  title: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    fontSize: '15px',
    fontWeight: 600,
  },
  icon: {
    fontSize: '18px',
  },
  modelTag: {
    fontSize: '10px',
    padding: '2px 8px',
    background: '#1e3a5f',
    borderRadius: '4px',
    color: '#38bdf8',
    fontWeight: 400,
  },
  status: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  statusDot: {
    width: '8px',
    height: '8px',
    borderRadius: '50%',
  },
  statusText: {
    color: '#94a3b8',
    fontSize: '12px',
  },
  refreshBtn: {
    padding: '4px 8px',
    background: '#334155',
    border: 'none',
    borderRadius: '4px',
    color: '#e2e8f0',
    fontSize: '11px',
    cursor: 'pointer',
  },
  main: {
    display: 'flex',
    flex: 1,
    overflow: 'hidden',
  },
  leftPanel: {
    width: '320px',
    padding: '16px',
    borderRight: '1px solid #334155',
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
  },
  dropZone: {
    flex: 1,
    minHeight: '200px',
    border: '2px dashed #334155',
    borderRadius: '8px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    transition: 'border-color 0.2s',
  },
  dropZoneActive: {
    borderColor: '#38bdf8',
  },
  dropZoneText: {
    textAlign: 'center',
    color: '#64748b',
  },
  dropIcon: {
    fontSize: '32px',
    marginBottom: '8px',
  },
  dropSubtext: {
    fontSize: '11px',
    marginTop: '4px',
  },
  previewImage: {
    maxWidth: '100%',
    maxHeight: '200px',
    objectFit: 'contain',
  },
  clearBtn: {
    padding: '6px 12px',
    background: '#3a1e1e',
    border: '1px solid #ef4444',
    borderRadius: '4px',
    color: '#ef4444',
    fontSize: '12px',
    cursor: 'pointer',
  },
  options: {
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
  },
  optionGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  label: {
    fontSize: '11px',
    color: '#94a3b8',
    fontWeight: 500,
  },
  select: {
    padding: '8px 10px',
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: '6px',
    color: '#e2e8f0',
    fontSize: '12px',
  },
  radioGroup: {
    display: 'flex',
    gap: '16px',
  },
  radioLabel: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    fontSize: '12px',
    cursor: 'pointer',
  },
  rightPanel: {
    flex: 1,
    padding: '16px',
    overflow: 'auto',
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
  },
  tabs: {
    display: 'flex',
    gap: '8px',
    borderBottom: '1px solid #334155',
    paddingBottom: '8px',
  },
  tab: {
    padding: '8px 16px',
    background: 'transparent',
    border: 'none',
    borderRadius: '6px 6px 0 0',
    color: '#64748b',
    fontSize: '12px',
    cursor: 'pointer',
  },
  tabActive: {
    background: '#1e293b',
    color: '#38bdf8',
  },
  error: {
    padding: '10px 12px',
    background: '#3a1e1e',
    borderRadius: '6px',
    color: '#ef4444',
    fontSize: '12px',
  },
  analyzeBtn: {
    padding: '12px 20px',
    background: '#22c55e',
    border: 'none',
    borderRadius: '8px',
    color: '#fff',
    fontSize: '13px',
    fontWeight: 600,
    cursor: 'pointer',
  },
  analyzeBtnDisabled: {
    background: '#334155',
    cursor: 'not-allowed',
  },
  singleButtons: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '8px',
  },
  taskBtn: {
    padding: '8px 12px',
    background: '#1e3a5f',
    border: '1px solid #38bdf8',
    borderRadius: '6px',
    color: '#38bdf8',
    fontSize: '12px',
    cursor: 'pointer',
  },
  loading: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    padding: '16px',
    color: '#94a3b8',
  },
  spinner: {
    width: '20px',
    height: '20px',
    border: '2px solid #334155',
    borderTopColor: '#38bdf8',
    borderRadius: '50%',
    animation: 'spin 1s linear infinite',
  },
  results: {
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
  },
  resultsTitle: {
    fontSize: '14px',
    fontWeight: 600,
    color: '#e2e8f0',
    marginBottom: '4px',
  },
  resultCard: {
    background: '#1e293b',
    borderRadius: '8px',
    border: '1px solid #334155',
    overflow: 'hidden',
  },
  resultHeader: {
    padding: '8px 12px',
    background: '#0f172a',
    fontSize: '12px',
    fontWeight: 600,
    color: '#38bdf8',
    borderBottom: '1px solid #334155',
  },
  resultContent: {
    padding: '12px',
    maxHeight: '200px',
    overflow: 'auto',
  },
  resultText: {
    margin: 0,
    fontSize: '12px',
    color: '#e2e8f0',
    whiteSpace: 'pre-wrap',
  },
  resultJson: {
    margin: 0,
    fontSize: '11px',
    color: '#94a3b8',
    fontFamily: 'monospace',
    whiteSpace: 'pre-wrap',
  },
  emptyState: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#475569',
    textAlign: 'center',
  },
  emptyIcon: {
    fontSize: '48px',
    marginBottom: '12px',
  },
  emptySubtext: {
    fontSize: '11px',
    marginTop: '8px',
    maxWidth: '300px',
  },
};
