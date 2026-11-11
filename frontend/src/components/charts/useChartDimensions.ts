import { useState, useEffect, useRef, useMemo } from 'react';
import { ChartDimensions, ChartMargin } from './types';

const DEFAULT_MARGIN: ChartMargin = { top: 16, right: 20, bottom: 32, left: 44 };

export function useChartDimensions(
  customMargin: Partial<ChartMargin> = {},
  defaultHeight: number = 260
) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  const marginTop = customMargin.top;
  const marginRight = customMargin.right;
  const marginBottom = customMargin.bottom;
  const marginLeft = customMargin.left;

  const margin: ChartMargin = useMemo(
    () => ({
      top: marginTop ?? DEFAULT_MARGIN.top,
      right: marginRight ?? DEFAULT_MARGIN.right,
      bottom: marginBottom ?? DEFAULT_MARGIN.bottom,
      left: marginLeft ?? DEFAULT_MARGIN.left,
    }),
    [marginTop, marginRight, marginBottom, marginLeft]
  );

  const [dimensions, setDimensions] = useState<ChartDimensions>({
    width: 500,
    height: defaultHeight,
    plotWidth: Math.max(0, 500 - margin.left - margin.right),
    plotHeight: Math.max(0, defaultHeight - margin.top - margin.bottom),
    margin,
  });

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;

    const updateDimensions = () => {
      const rect = element.getBoundingClientRect();
      const width = Math.max(200, Math.floor(rect.width));
      const height = defaultHeight;

      setDimensions({
        width,
        height,
        plotWidth: Math.max(0, width - margin.left - margin.right),
        plotHeight: Math.max(0, height - margin.top - margin.bottom),
        margin,
      });
    };

    updateDimensions();

    const resizeObserver = new ResizeObserver(() => {
      updateDimensions();
    });

    resizeObserver.observe(element);
    return () => {
      resizeObserver.disconnect();
    };
  }, [defaultHeight, margin]);

  return { containerRef, dimensions };
}
