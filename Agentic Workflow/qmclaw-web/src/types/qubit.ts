/**
 * QubitClient Service Type Definitions
 */

// 实验家族
export interface ExperimentFamily {
  id: string;
  name: string;
  description: string;
}

// 图表描述结果 (Q1)
export interface DescribePlotResult {
  plot_type: 'scatter' | 'line' | 'heatmap' | 'histogram' | 'image';
  x_axis: {
    label: string;
    scale?: 'linear' | 'log';
    range?: [number, number];
    unit?: string;
  };
  y_axis: {
    label: string;
    scale?: 'linear' | 'log';
    range?: [number, number];
    unit?: string;
  };
  main_features: string;
  colorbar?: { label: string };
}

// 分类结果 (Q2)
export interface ClassifyOutcomeResult {
  Classification: 'Expected' | 'Suboptimal' | 'Anomalous' | 'Apparatus issue' | string;
  Confidence?: number;
  Reason?: string;
}

// 评估拟合结果 (Q4)
export interface AssessFitResult {
  Assessment: 'Reliable' | 'Unreliable' | string;
  FitQuality?: string;
  Comments?: string;
}

// 提取参数结果 (Q5)
export interface ExtractParamsResult {
  [key: string]: string | number | boolean | object;
}

// 评估状态结果 (Q6)
export interface EvaluateStatusResult {
  Status: 'SUCCESS' | 'NO_SIGNAL' | 'BAD_FIT' | 'MISCALIBRATED' | 'NO_GATE' | string;
  Diagnosis?: string;
  Recommendations?: string;
}

// 完整分析结果
export interface FullAnalysisResult {
  describe_plot?: DescribePlotResult | string;
  classify_outcome?: ClassifyOutcomeResult | string;
  scientific_reasoning?: string;
  assess_fit?: AssessFitResult | string;
  extract_params?: ExtractParamsResult | string;
  evaluate_status?: EvaluateStatusResult | string;
}

// API 响应
export interface QubitApiResponse<T = any> {
  success: boolean;
  task?: string;
  experiment_family?: string;
  result?: T;
  results?: FullAnalysisResult;
  error?: string;
  errors?: Record<string, string>;
}

// 图像分析请求
export interface AnalyzeRequest {
  image: string; // base64 编码的图像
  experiment_family: string;
  language?: 'en' | 'zh';
}

// 健康检查响应
export interface HealthResponse {
  status: 'healthy' | 'degraded';
  service: string;
  initialized: boolean;
  model: string;
  base_url: string;
  error?: string;
}

// 实验家族列表响应
export interface FamiliesResponse {
  families: ExperimentFamily[];
  count: number;
}
