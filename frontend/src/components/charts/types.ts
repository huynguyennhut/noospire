export interface ChartMargin {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

export interface ChartDimensions {
  width: number;
  height: number;
  plotWidth: number;
  plotHeight: number;
  margin: ChartMargin;
}

export interface AreaSeriesConfig {
  id: string;
  name: string;
  color: string;
  dataKey: string;
  dashed?: boolean;
}

export interface BarSeriesConfig {
  id: string;
  name: string;
  color: string;
  dataKey: string;
}

export interface DonutSegmentItem {
  id: string;
  label: string;
  value: number;
  color: string;
  formattedValue?: string;
}

export interface GaugeZone {
  max: number;
  label: string;
  color: string;
}

export interface TooltipPayloadItem {
  name: string;
  value: number | string;
  color: string;
}
