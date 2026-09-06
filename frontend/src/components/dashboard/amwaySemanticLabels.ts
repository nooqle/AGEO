export const semanticTypeLabels: Record<string, string> = {
  brand: '品牌', organization: '组织', product: '产品', material: '原料', tool: '工具',
  person: '人物', concept: '概念', topic: '主题', unresolved: '身份未定',
  document: '文献', event: '活动', place: '场所', program: '项目',
};
export const semanticRelationLabels: Record<string, string> = {
  contains: '包含', produced_by: '生产方', authored_by: '作者', supports: '支持',
  used_by: '使用方', associated_with: '相关', part_of: '组成部分所属',
  uses_technology: '采用技术', hosted_by: '主办方',
};
export const lexiconStatusLabels: Record<string, string> = {
  approved: '词条已确认', pending_review: '词条待复核', rejected: '词条已排除', merged: '词条已合并',
};
