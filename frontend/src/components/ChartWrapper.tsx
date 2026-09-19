"use client";

import React, { useEffect, useRef } from "react";
import * as echarts from "echarts";

interface ChartWrapperProps {
  option: echarts.EChartsOption;
  height?: string | number;
  className?: string;
  loading?: boolean;
}

export function ChartWrapper({
  option,
  height = "360px",
  className = "",
  loading = false,
}: ChartWrapperProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!chartRef.current) return;

    if (!chartInstance.current) {
      chartInstance.current = echarts.init(chartRef.current);
    }

    if (loading) {
      chartInstance.current.showLoading();
    } else {
      chartInstance.current.hideLoading();
      chartInstance.current.setOption(option, true);
    }

    const handleResize = () => {
      chartInstance.current?.resize();
    };

    const resizeObserver = new ResizeObserver(() => {
      chartInstance.current?.resize();
    });
    resizeObserver.observe(chartRef.current);
    window.addEventListener("resize", handleResize);

    return () => {
      resizeObserver.disconnect();
      window.removeEventListener("resize", handleResize);
    };
  }, [option, loading]);

  useEffect(() => {
    return () => {
      chartInstance.current?.dispose();
      chartInstance.current = null;
    };
  }, []);

  return (
    <div
      ref={chartRef}
      className={`w-full ${className}`}
      style={{ height: typeof height === "number" ? `${height}px` : height }}
    />
  );
}
