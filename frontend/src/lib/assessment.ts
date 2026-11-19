import type { Asset } from './types';

/** Admission is decided by the API, never inferred from a DNS suffix or VERIFIED. */
export function assessmentEligible(asset: Pick<Asset, 'assessment_eligible'>): boolean {
  return asset.assessment_eligible === true;
}

export function assessmentLabel(asset: Pick<Asset, 'assessment_eligible' | 'assessment_block_reason' | 'inventory_classification'>, vi: boolean): string {
  if (assessmentEligible(asset)) return vi ? 'Đủ điều kiện đánh giá' : 'Eligible for assessment';
  if (asset.inventory_classification === 'SEEDED_OR_TEST' || asset.assessment_block_reason === 'SYNTHETIC_INVENTORY')
    return vi ? 'Dữ liệu mẫu / kiểm thử — không quét khách hàng' : 'Seeded / test data — excluded from customer scans';
  if (asset.assessment_block_reason === 'SEEDED_OWNERSHIP_NOT_VERIFIED')
    return vi ? 'Bản ghi khởi tạo — cần đối chiếu quyền sở hữu' : 'Seeded record — ownership reconciliation needed';
  if (asset.assessment_block_reason === 'TARGET_EMERGENCY_STOP') return vi ? 'Đã dừng khẩn mục tiêu' : 'Target emergency stop active';
  if (asset.assessment_block_reason === 'SCOPE_EXPIRED') return vi ? 'Phạm vi đã hết hạn' : 'Assessment scope expired';
  if (asset.assessment_block_reason === 'NO_ASSESSMENT_SCOPE') return vi ? 'Chưa có phạm vi được duyệt' : 'No approved assessment scope';
  if (asset.assessment_block_reason === 'OWNERSHIP_NOT_VERIFIED') return vi ? 'Chưa xác minh quyền sở hữu' : 'Ownership not verified';
  return vi ? 'Chưa đủ điều kiện — cần đối chiếu phạm vi và chính sách' : 'Not eligible — reconcile scope and policy';
}

export function eligibleAssetIds(assets: Asset[]): string[] {
  return assets.filter(assessmentEligible).map((asset) => asset.id);
}

/** Offline artifact admission must not grant permission to contact a target. */
export function engineEligible(asset: Pick<Asset, 'assessment_eligible' | 'artifact_analysis_eligible'>, engine: string): boolean {
  return engine === 'sbom' ? asset.artifact_analysis_eligible === true : assessmentEligible(asset);
}

export function engineAssetIds(assets: Asset[], engines: string[]): string[] {
  return assets.filter((asset) => engines.some((engine) => engineEligible(asset, engine))).map((asset) => asset.id);
}
