import type { SensorPointOut } from "../api/types";
import { readingAvailable } from "./status";

export function SensorSparkline({
  readings,
  className = "h-8 w-full",
  stroke = "#F5A524",
}: {
  readings: SensorPointOut[];
  className?: string;
  stroke?: string;
}) {
  // Only good-quality readings are plotted; suspect or missing values would draw a false trend.
  const values = readings.filter(readingAvailable).map((reading) => reading.value);
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = 100 / (values.length - 1);
  const points = values
    .map((value, index) => `${(index * step).toFixed(1)},${(26 - ((value - min) / span) * 24).toFixed(1)}`)
    .join(" ");
  return (
    <svg className={className} viewBox="0 0 100 28" preserveAspectRatio="none" aria-hidden="true">
      <polyline points={points} fill="none" stroke={stroke} strokeWidth="1.8" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
