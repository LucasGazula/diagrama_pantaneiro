export interface UserRead {
  id: string;
  email: string;
  is_active: boolean;
  is_superuser: boolean;
  is_verified: boolean;
}

export interface JwtLoginResponse {
  access_token: string;
  token_type: "bearer";
}

export interface ApiErrorBody {
  detail: string | Array<{ msg: string; loc: unknown }>;
}

export interface PositionOut {
  id: string;
  name: string;
  assetType: string;
  amount: number;
  currentPrice: number | null;
  currentValueBrl: number;
  strength: number;
  diagramResponses: string[] | null;
  source: string;
  updatedAt?: string | null;
  trackingMode?: "balance" | "units";
  externalId?: string | null;
  quoteAsOf?: string | null;
  quoteStale?: boolean;
}

export interface TargetOut {
  id: string;
  assetType: string;
  targetPercentage: number;
}

export interface AporteAllocationOut {
  id: string;
  positionId: string | null;
  positionNameSnapshot: string;
  assetTypeSnapshot: string;
  priceAtAporteBrl: number | null;
  trackingModeSnapshot?: "balance" | "units" | null;
  suggestedValueBrl: number;
  suggestedQuantity: number;
  applied: boolean;
  appliedAt: string | null;
  appliedValueBrl: number | null;
  appliedQuantity: number | null;
  excluded: boolean;
}

export interface AporteEventOut {
  id: string;
  aporteValueBrl: number;
  createdAt: string;
  allocations: AporteAllocationOut[];
}

export interface PositionCreate {
  trackingMode?: "balance" | "units";
  externalId?: string | null;
  name: string;
  assetType: string;
  amount: number;
  currentPrice?: number | null;
  strength: number;
  diagramResponses?: string[] | null;
}

export interface PositionUpdate {
  name?: string;
  externalId?: string | null;
  trackingMode?: "balance" | "units";
  amount?: number;
  currentPrice?: number | null;
  strength?: number;
  diagramResponses?: string[] | null;
}

export interface DiagramQuestionOut {
  id: string;
  diagramType: string;
  criterias: string;
  questionText: string;
  displayOrder: number;
  externalId: string | null;
}

export interface DiagramQuestionCreate {
  diagramType: string;
  criterias?: string;
  questionText: string;
  displayOrder?: number | null;
}

export interface DiagramQuestionUpdate {
  criterias?: string;
  questionText?: string;
  displayOrder?: number;
}

export interface PriceFailureOut {
  name: string;
  reason: string;
}

export interface RefreshSummaryOut {
  refreshed: number;
  skippedManual: number;
  failed: PriceFailureOut[];
  stale?: PriceFailureOut[];
}

export interface CandidateOut {
  externalId?: string | null;
  quoteAsOf?: string | null;
  name: string;
  label: string | null;
  currentPriceBrl: number | null;
}

export interface TargetUpdateIn {
  assetType: string;
  targetPercentage: number;
}

export interface TargetsUpdateBody {
  targets: TargetUpdateIn[];
}

export interface PresetOut {
  id: string;
  name: string;
  values: Record<string, number>;
  createdAt: string;
}

export interface PresetIn {
  name: string;
  values: Record<string, number>;
}

export interface PortfolioOut {
  id: string;
  name: string;
  isDefault: boolean;
  createdAt: string;
}

export interface PortfolioCreate {
  name: string;
}

export interface PortfolioRename {
  name: string;
}

export interface DividendItemOut {
  id: string;
  ticker: string;
  assetType: string;
  paymentDate: string;
  exDate: string | null;
  amountShares: number;
  rateNative: number;
  currency: string;
  rateBrl: number;
  rateNetBrl: number;
  totalNative: number;
  totalBrl: number;
  totalNetBrl: number;
  taxRate: number;
  taxBrl: number;
  isJcp: boolean;
  dividendType: string;
  status: "pago" | "previsto";
}

export interface DividendCalendarOut {
  year: number;
  month: number;
  dateMode: "payment" | "ex";
  usdRate: number;
  totalReceivedBrl: number;
  totalReceivedNetBrl: number;
  totalProjectedBrl: number;
  totalProjectedNetBrl: number;
  totalMonthBrl: number;
  totalMonthNetBrl: number;
  totalTaxBrl: number;
  items: DividendItemOut[];
}

export interface DividendSyncOut {
  syncedTickers: number;
  failedTickers: string[];
  totalDividendsStored: number;
}
