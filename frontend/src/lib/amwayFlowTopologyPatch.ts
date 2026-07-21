/**
 * 3c-B: deterministic topology patch presets (no NL / no LLM).
 * Mirrors backend app.workflow.topology_patch.PRESET_INTENTS labels.
 */

export type TopologyPatchIntentId =
  | 'skip_doubao'
  | 'enable_all_platforms'
  | 'add_projection_analysis';

export type TopologyPatchPreset = {
  intentId: TopologyPatchIntentId;
  label: string;
  hint: string;
};

export const TOPOLOGY_PATCH_PRESETS: TopologyPatchPreset[] = [
  {
    intentId: 'skip_doubao',
    label: '跳过豆包',
    hint: '断开豆包采集连线，下次运行不抓取豆包',
  },
  {
    intentId: 'enable_all_platforms',
    label: '恢复全部平台',
    hint: '恢复 deepseek / kimi / doubao / hunyuan 采集连线',
  },
  {
    intentId: 'add_projection_analysis',
    label: '加图谱分析节点',
    hint: '在图谱后挂一个数据分析节点并连线',
  },
];
